package providers

import (
	"fmt"
	"math"
	"strings"
	"sync"
	"time"

	"github.com/Buco7854/carhibou/agent/internal/model"
	"github.com/Buco7854/carhibou/agent/internal/profile"
)

// connectRetryInterval throttles reconnection to an adapter that is not
// answering. Connecting is several serial exchanges; attempting it on every
// sample means an agent with an unplugged adapter spends most of its single
// core timing out, which delays the position samples it could still be taking.
const connectRetryInterval = 60 * time.Second

// canProtocols are tried in order until one carries frames.
//
// Monitoring is passive, so the adapter cannot discover the protocol the way a
// request would: it has to be told, and told correctly, or it listens to a bus
// nobody is speaking on. These four are the CAN variants an OBD port can carry;
// most vehicles built this century are the first.
var canProtocols = []struct {
	code        string
	description string
}{
	{"6", "CAN 11-bit, 500 kbit/s"},
	{"7", "CAN 29-bit, 500 kbit/s"},
	{"8", "CAN 11-bit, 250 kbit/s"},
	{"9", "CAN 29-bit, 250 kbit/s"},
}

// protocolTrial is how long a protocol is given to produce a frame before the
// next is tried. A vehicle broadcasting at all repeats within this.
const protocolTrial = 2 * time.Second

type ProfileProvider struct {
	adapter *OBDAdapter
	decoder *profile.DecoderEngine
	trial   time.Duration
	allowed map[int]struct{}

	mutex         sync.Mutex
	observations  model.MetricObservations
	lastFrame     time.Time
	lastDecoded   time.Time
	failure       string
	unfiltered    bool
	baseReport    MonitorReport
	monitorReport MonitorReport

	stop    chan struct{}
	stopped sync.WaitGroup
	nextTry time.Time
}

func NewProfileProvider(adapter *OBDAdapter, decoder *profile.DecoderEngine) *ProfileProvider {
	allowed := make(map[int]struct{})
	for _, canID := range decoder.CANIDs() {
		allowed[canID] = struct{}{}
	}
	return &ProfileProvider{
		adapter: adapter, decoder: decoder, trial: protocolTrial,
		allowed: allowed, observations: model.MetricObservations{},
	}
}

// Status explains why the provider is publishing nothing.
//
// Every failure here is recoverable and none of it should stop an agent
// reporting its position, so ReadObservations returns what it has rather than an
// error. That made a permanently disconnected adapter invisible: the vehicle
// published position and health forever and simply never mentioned CAN.
func (provider *ProfileProvider) Status() string {
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	return provider.failure
}

// State names a working-but-degraded monitor without turning that condition
// into a connection failure that the retrying owner would tear down.
func (provider *ProfileProvider) State() string {
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	parts := []string{}
	silent := provider.stop != nil && (provider.lastDecoded.IsZero() || time.Since(provider.lastDecoded) > provider.trial)
	if provider.unfiltered {
		parts = append(parts, "unfiltered monitor; hardware filters ineffective")
	}
	if silent {
		parts = append(parts, fmt.Sprintf("monitoring, 0 profile frames decoded in last %s", provider.trial))
	}
	if (provider.unfiltered || silent) && provider.monitorReport.MalformedFrames > 0 {
		parts = append(parts, fmt.Sprintf("%d malformed monitor lines", provider.monitorReport.MalformedFrames))
	}
	if (provider.unfiltered || silent) && provider.monitorReport.DataErrors > 0 {
		parts = append(parts, fmt.Sprintf("%d data-error-marked frames retained", provider.monitorReport.DataErrors))
	}
	if (provider.unfiltered || silent) && provider.monitorReport.AdapterErrors > 0 {
		parts = append(parts, fmt.Sprintf("%d adapter error lines", provider.monitorReport.AdapterErrors))
	}
	if (provider.unfiltered || silent) && provider.monitorReport.BufferFull {
		parts = append(parts, "adapter buffer overflowed")
	}
	return strings.Join(parts, "; ")
}

// Live reports whether a frame arrived recently.
//
// The decoded metrics cannot answer this: they are the last known values and are
// republished unchanged after the bus goes quiet, so a parked vehicle looks from
// the metrics alone exactly like a moving one.
func (provider *ProfileProvider) Live() bool {
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	return !provider.lastFrame.IsZero() && time.Since(provider.lastFrame) < provider.trial
}

// ReadObservations returns the values the background monitor has collected.
//
// It does not wait for the bus. Frames arrive continuously whether or not anyone
// is reading, so sampling is a snapshot of what the monitor has kept current: a
// one-second cadence is a one-second cadence, rather than a second of listening
// plus everything else the sample needs.
func (provider *ProfileProvider) ReadObservations() (model.MetricObservations, error) {
	provider.Start()
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	return copyObservations(provider.observations), nil
}

// Start connects and begins monitoring eagerly. ReadObservations also calls it
// so direct users that do not own the provider lifecycle remain safe.
func (provider *ProfileProvider) Start() {
	provider.mutex.Lock()
	running := provider.stop != nil
	waiting := time.Now().Before(provider.nextTry)
	if running || waiting {
		provider.mutex.Unlock()
		return
	}
	provider.nextTry = time.Now().Add(connectRetryInterval)
	provider.mutex.Unlock()

	if err := provider.adapter.Connect(); err != nil {
		provider.fail(fmt.Sprintf("device %s failed to open: %v", provider.adapter.device, err))
		return
	}
	preparation, err := PrepareProfileMonitor(
		provider.adapter, provider.decoder.CANIDs(), provider.trial, 0, false, provider.record,
	)
	if err != nil {
		provider.adapter.Close()
		provider.fail(err.Error())
		return
	}

	stop := make(chan struct{})
	provider.mutex.Lock()
	provider.stop = stop
	provider.failure = ""
	provider.unfiltered = preparation.UseUnfiltered
	provider.baseReport = preparationMonitorReport(preparation)
	provider.monitorReport = provider.baseReport
	provider.mutex.Unlock()

	provider.stopped.Add(1)
	go func() {
		defer provider.stopped.Done()
		err := provider.adapter.MonitorUntilWithReport(
			stop, preparation.UseUnfiltered, provider.record, provider.updateMonitorReport,
		)
		provider.mutex.Lock()
		provider.stop = nil
		if err != nil {
			provider.failure = "CAN monitoring stopped on " + preparation.Protocol + ": " + err.Error()
		}
		provider.mutex.Unlock()
		provider.adapter.Close()
	}()
}
func (provider *ProfileProvider) record(frame model.CANFrame) {
	if _, ok := provider.allowed[frame.CANID]; !ok {
		return
	}
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	observedAt := frameTime(frame)
	provider.lastFrame = observedAt
	next := copyObservations(provider.observations)
	decodedValues := provider.decoder.Decode(frame, observationValues(provider.observations))
	if len(decodedValues) > 0 {
		provider.lastDecoded = observedAt
	}
	for _, decoded := range decodedValues {
		metricObservedAt := observedAt
		if decoded.Method == model.MethodDerived {
			for _, input := range decoded.Inputs {
				observation, ok := next[input]
				if ok && observation.Metadata.ObservedAt.Before(metricObservedAt) {
					metricObservedAt = observation.Metadata.ObservedAt
				}
			}
		}
		next[decoded.Name] = model.MetricObservation{
			Value: decoded.Value,
			Metadata: model.ObservationMetadata{
				ObservedAt: metricObservedAt,
				Channel:    model.ChannelCAN,
				Method:     decoded.Method,
			},
		}
	}
	provider.observations = next
}

func (provider *ProfileProvider) updateMonitorReport(report MonitorReport) {
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	provider.monitorReport = mergeMonitorReports(provider.baseReport, report)
}

func (provider *ProfileProvider) fail(reason string) {
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	provider.failure = reason
}

func (provider *ProfileProvider) Close() {
	provider.mutex.Lock()
	stop := provider.stop
	provider.stop = nil
	provider.mutex.Unlock()
	if stop != nil {
		close(stop)
		provider.stopped.Wait()
		return
	}
	provider.adapter.Close()
}

func observationValues(source model.MetricObservations) map[string]any {
	values := make(map[string]any, len(source))
	for key, observation := range source {
		values[key] = observation.Value
	}
	return values
}

func copyObservations(source model.MetricObservations) model.MetricObservations {
	result := model.MetricObservations{}
	for key, observation := range source {
		result[key] = observation
	}
	return result
}

func frameTime(frame model.CANFrame) time.Time {
	if frame.Timestamp <= 0 || math.IsNaN(frame.Timestamp) || math.IsInf(frame.Timestamp, 0) {
		return time.Now().UTC()
	}
	seconds := int64(frame.Timestamp)
	nanoseconds := int64((frame.Timestamp - float64(seconds)) * float64(time.Second))
	return time.Unix(seconds, nanoseconds).UTC()
}
