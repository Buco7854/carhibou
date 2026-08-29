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

const (
	// auxVoltageInterval paces the adapter's own supply reading. It answers with
	// the vehicle asleep, which is the whole point of it, so it is the one thing
	// worth asking for on a bus that has gone quiet. Asking often would interrupt
	// the frame stream for nothing: a 12V battery does not move quickly.
	auxVoltageInterval = 5 * time.Minute
	// auxVoltageTimeout bounds one interleaved reading so a wedged adapter cannot
	// stall the monitor.
	auxVoltageTimeout = 10 * time.Second
	// auxVoltageFailureLimit is how many consecutive unanswered readings mean the
	// adapter itself has gone, rather than one reading being lost to a busy bus.
	auxVoltageFailureLimit = 3
	// eventDebounce is the shortest gap between two event-triggered samples. A
	// signal that chatters at frame rate must not turn into an upload storm.
	eventDebounce = 30 * time.Second
)

// AuxVoltageMetric is the canonical name for the adapter's supply reading. It is
// the 12V accessory battery, not the traction pack, and it is measured by the
// adapter rather than reported by the vehicle, so its channel is obd.
const AuxVoltageMetric = "battery.aux_voltage"

// eventMetrics are the decoded names whose change is worth a sample of its own.
//
// They are the canonical state declarations a profile already makes, so this
// needs no new profile field: readiness, charging, and whatever operating state
// the vehicle names. A value moving inside its range is cadence work; one of
// these flipping is news, and waiting out a parked cadence to report it is how a
// charge that started at 02:00 first appears at 02:10.
var eventMetrics = []string{"vehicle.ready", "charging.active", "vehicle.in_use", "vehicle.state"}

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

	voltageInterval time.Duration
	voltageTimeout  time.Duration
	lastVoltageAt   time.Time
	voltageFailures int
	attached        bool

	eventValues map[string]any
	eventReason string
	lastEventAt time.Time
	eventGap    time.Duration
	voltageStop chan struct{}
	voltageDone sync.WaitGroup

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
		voltageInterval: auxVoltageInterval, voltageTimeout: auxVoltageTimeout,
		eventGap: eventDebounce, eventValues: map[string]any{},
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
		parts = append(parts, provider.quietDescription())
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

// quietDescription says how long the bus has been silent while the monitor is
// still running. A vehicle asleep overnight is the ordinary case, so the reading
// names the duration rather than implying a fault. The caller holds the mutex.
func (provider *ProfileProvider) quietDescription() string {
	if provider.lastFrame.IsZero() {
		return "monitoring, bus quiet since start"
	}
	quiet := time.Since(provider.lastFrame).Round(time.Second)
	return fmt.Sprintf("monitoring, bus quiet for %s", quiet)
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
	// Read the supply before the stream starts. It is the one value available with
	// the vehicle asleep, so a bus that never speaks still produces a sample with
	// something true in it from the first collection onwards.
	provider.readVoltage()
	preparation, err := PrepareProfileMonitor(
		provider.adapter, provider.decoder.CANIDs(), provider.trial, 0, false, provider.record,
		nil, time.Time{},
	)
	if err != nil {
		provider.adapter.Close()
		provider.fail(err.Error())
		return
	}

	stop := make(chan struct{})
	voltageStop := make(chan struct{})
	provider.mutex.Lock()
	provider.stop = stop
	provider.voltageStop = voltageStop
	provider.failure = ""
	provider.unfiltered = preparation.UseUnfiltered
	provider.baseReport = preparationMonitorReport(preparation)
	provider.monitorReport = provider.baseReport
	provider.mutex.Unlock()

	provider.voltageDone.Add(1)
	go provider.pollVoltage(voltageStop)

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
	provider.noteEvents(next, observedAt)
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
	voltageStop := provider.voltageStop
	provider.stop = nil
	provider.voltageStop = nil
	provider.mutex.Unlock()
	// The supply poll interleaves itself with the monitor, so it has to be gone
	// before the monitor is asked to stop or its request outlives its server.
	if voltageStop != nil {
		close(voltageStop)
		provider.voltageDone.Wait()
	}
	if stop != nil {
		close(stop)
		provider.stopped.Wait()
		return
	}
	provider.adapter.Close()
}

// pollVoltage keeps the adapter's own supply reading current.
//
// The reading is served by the monitor goroutine because that goroutine owns the
// port. On a bus that has gone quiet this is the only traffic the adapter sees,
// and it is what separates a sleeping vehicle from an adapter somebody unplugged.
func (provider *ProfileProvider) pollVoltage(stop <-chan struct{}) {
	defer provider.voltageDone.Done()
	ticker := time.NewTicker(provider.voltageInterval)
	defer ticker.Stop()
	for {
		select {
		case <-stop:
			return
		case <-ticker.C:
			provider.readVoltage()
		}
	}
}

// readVoltage takes one supply reading, interleaving it with the frame stream
// when a monitor is running and taking the port directly when one is not.
func (provider *ProfileProvider) readVoltage() {
	var reading string
	var err error
	take := func(adapter *OBDAdapter) { reading, err = adapter.Voltage() }
	if !provider.adapter.DuringMonitor(take, provider.voltageTimeout) {
		provider.mutex.Lock()
		monitoring := provider.stop != nil
		provider.mutex.Unlock()
		if monitoring {
			// A monitor is running but did not serve the request in time. That is
			// a busy adapter, not a missing one, so it is not counted against it.
			return
		}
		take(provider.adapter)
	}
	value, ok := ParseSupplyVoltage(reading)
	if err != nil || !ok {
		provider.recordVoltageFailure()
		return
	}
	provider.storeVoltage(value)
}

func (provider *ProfileProvider) storeVoltage(value float64) {
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	now := time.Now().UTC()
	provider.voltageFailures = 0
	provider.attached = true
	provider.lastVoltageAt = now
	next := copyObservations(provider.observations)
	next[AuxVoltageMetric] = model.MetricObservation{
		Value: value,
		Metadata: model.ObservationMetadata{
			ObservedAt: now,
			Channel:    model.ChannelOBD,
			Method:     model.MethodDirect,
		},
	}
	provider.observations = next
}

// recordVoltageFailure turns repeated silence from the adapter into a failure.
//
// One lost reading is a busy bus. Several in a row is the adapter itself gone,
// which is the only condition under which the values it decoded stop being
// observations rather than merely ageing ones.
func (provider *ProfileProvider) recordVoltageFailure() {
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	provider.voltageFailures++
	if provider.voltageFailures < auxVoltageFailureLimit {
		return
	}
	provider.attached = false
	if provider.failure == "" {
		provider.failure = fmt.Sprintf(
			"adapter stopped answering its supply reading %d times running",
			provider.voltageFailures,
		)
	}
}

// Attached reports whether the adapter itself is still answering.
//
// It is deliberately not Live: a vehicle that has gone to sleep stops
// broadcasting while its adapter keeps answering, and those two facts have
// opposite consequences for the values already reported.
func (provider *ProfileProvider) Attached() bool {
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	if provider.failure != "" {
		return false
	}
	// Before the first reading the adapter has only just been opened, which is
	// itself evidence that it is there.
	return provider.attached || provider.lastVoltageAt.IsZero()
}

// TakeEvent returns and clears the reason a sample is owed right now.
func (provider *ProfileProvider) TakeEvent() string {
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	reason := provider.eventReason
	provider.eventReason = ""
	return reason
}

// noteEvents records a state change worth reporting before the cadence would.
//
// Only a change counts, and only one within the debounce window, so a signal
// that chatters between two values at frame rate costs one extra sample rather
// than thousands. The caller holds the mutex.
func (provider *ProfileProvider) noteEvents(next model.MetricObservations, at time.Time) {
	for _, key := range eventMetrics {
		observation, present := next[key]
		if !present {
			continue
		}
		previous, seen := provider.eventValues[key]
		provider.eventValues[key] = observation.Value
		if !seen || previous == observation.Value {
			continue
		}
		if !provider.lastEventAt.IsZero() && at.Sub(provider.lastEventAt) < provider.eventGap {
			continue
		}
		provider.lastEventAt = at
		provider.eventReason = fmt.Sprintf("%s changed to %v", key, observation.Value)
		return
	}
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
