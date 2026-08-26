package providers

import (
	"fmt"
	"sync"
	"time"

	"github.com/Buco7854/vehinode/agent/internal/model"
	"github.com/Buco7854/vehinode/agent/internal/profile"
)

// connectRetryInterval throttles reconnection to an adapter that is not
// answering. Connecting is several serial exchanges; attempting it on every
// sample means a tracker with an unplugged adapter spends most of its single
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

	mutex     sync.Mutex
	metrics   map[string]any
	lastFrame time.Time
	failure   string

	stop    chan struct{}
	stopped sync.WaitGroup
	nextTry time.Time
}

func NewProfileProvider(adapter *OBDAdapter, decoder *profile.DecoderEngine) *ProfileProvider {
	return &ProfileProvider{adapter: adapter, decoder: decoder, metrics: map[string]any{}}
}

// Status explains why the provider is publishing nothing.
//
// Every failure here is recoverable and none of it should stop a tracker
// reporting its position, so ReadMetrics returns what it has rather than an
// error. That made a permanently disconnected adapter invisible: the vehicle
// published position and health forever and simply never mentioned CAN.
func (provider *ProfileProvider) Status() string {
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	return provider.failure
}

// Live reports whether a frame arrived recently.
//
// The decoded metrics cannot answer this: they are the last known values and are
// republished unchanged after the bus goes quiet, so a parked vehicle looks from
// the metrics alone exactly like a moving one.
func (provider *ProfileProvider) Live() bool {
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	return !provider.lastFrame.IsZero() && time.Since(provider.lastFrame) < protocolTrial
}

// ReadMetrics returns the values the background monitor has collected.
//
// It does not wait for the bus. Frames arrive continuously whether or not anyone
// is reading, so sampling is a snapshot of what the monitor has kept current: a
// one-second cadence is a one-second cadence, rather than a second of listening
// plus everything else the sample needs.
func (provider *ProfileProvider) ReadMetrics() (map[string]any, error) {
	provider.start()
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	return copyMetrics(provider.metrics), nil
}

func (provider *ProfileProvider) start() {
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
		provider.fail("adapter did not connect: " + err.Error())
		return
	}
	if err := provider.adapter.PassFilters(provider.decoder.CANIDs()); err != nil {
		provider.adapter.Close()
		provider.fail("adapter rejected the CAN filters: " + err.Error())
		return
	}
	protocol, err := provider.selectListeningProtocol()
	if err != nil {
		provider.adapter.Close()
		provider.fail(err.Error())
		return
	}

	stop := make(chan struct{})
	provider.mutex.Lock()
	provider.stop = stop
	provider.failure = ""
	provider.mutex.Unlock()

	provider.stopped.Add(1)
	go func() {
		defer provider.stopped.Done()
		err := provider.adapter.MonitorUntil(stop, provider.record)
		provider.mutex.Lock()
		provider.stop = nil
		if err != nil {
			provider.failure = "CAN monitoring stopped on " + protocol + ": " + err.Error()
		}
		provider.mutex.Unlock()
		provider.adapter.Close()
	}()
}

// selectListeningProtocol finds one that actually carries traffic.
//
// A wrong protocol is silent rather than wrong, and silence is indistinguishable
// from a sleeping vehicle, so each is tried until frames appear. The last is kept
// when none do: a vehicle that is merely asleep should not have its protocol
// changed underneath it when it wakes.
func (provider *ProfileProvider) selectListeningProtocol() (string, error) {
	for _, protocol := range canProtocols {
		if err := provider.adapter.SelectProtocol(protocol.code); err != nil {
			continue
		}
		seen := false
		if err := provider.adapter.Monitor(protocolTrial, func(model.CANFrame) { seen = true }); err != nil {
			return "", fmt.Errorf("adapter stopped while listening: %w", err)
		}
		if seen {
			return protocol.description, nil
		}
	}
	// Nothing spoke. The first is the one almost every vehicle uses, so it is what
	// the monitor waits on rather than whichever happened to be tried last.
	if err := provider.adapter.SelectProtocol(canProtocols[0].code); err != nil {
		return "", fmt.Errorf("adapter rejected every CAN protocol: %w", err)
	}
	return canProtocols[0].description, nil
}

func (provider *ProfileProvider) record(frame model.CANFrame) {
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	provider.lastFrame = time.Now()
	for _, decoded := range provider.decoder.Decode(frame, provider.metrics) {
		provider.metrics[decoded.Name] = decoded.Value
	}
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

func copyMetrics(source map[string]any) map[string]any {
	result := map[string]any{}
	for key, value := range source {
		result[key] = value
	}
	return result
}
