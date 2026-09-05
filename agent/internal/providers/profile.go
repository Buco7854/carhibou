package providers

import (
	"errors"
	"fmt"
	"math"
	"strings"
	"sync"
	"time"

	"github.com/Buco7854/carhibou/agent/internal/model"
	"github.com/Buco7854/carhibou/agent/internal/profile"
	"github.com/Buco7854/carhibou/agent/internal/usbrecovery"
)

// servicePreparationTimeout bounds one preparation attempt against an adapter
// that stops answering partway through. It runs on the acquisition goroutine,
// so nothing samples or shuts down behind it; the only thing it must not do is
// cut a legitimate sequence short. The longest honest one is two protocol
// sweeps (four protocols at protocolTrial each, before and after a baud
// fallback) plus the two verification windows: about 20 s, and the deadline is
// only consulted between stages. 90 s leaves that with room for the adapter's
// own per-command timeouts.
const servicePreparationTimeout = 90 * time.Second

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
	// profileBurstWindow is the wake poll's full listen window and the ceiling for
	// sample bursts.
	profileBurstWindow = time.Second
	// minimumProfileBurstWindow hears every C-Zero identifier at least three
	// times because they repeat within 10-100 ms. Using one third of the sampling
	// interval leaves the serial line idle for two thirds of it, preserving the
	// separation from the continuous stream that could freeze the service.
	minimumProfileBurstWindow = 300 * time.Millisecond
	// monitorExitRoundTrip is what leaving STM costs when the adapter answers
	// promptly. It sizes how long a sample waits, not how long the adapter is
	// given: the exit itself keeps the ordinary command window, and one that runs
	// long times the waiter out into the carried snapshot instead of holding the
	// sample. That is what the carried snapshot is for.
	monitorExitRoundTrip = 200 * time.Millisecond
	// burstCompletionSlack keeps that bound strictly above the work it bounds. A
	// silent adapter measured 502 ms against a 500 ms allowance: two timers each
	// fire a little late, and the goroutine reading them is not scheduled the
	// instant they do.
	burstCompletionSlack = 100 * time.Millisecond
	// burstCompletionAllowance follows the two bounded operations around the
	// listen timer: one possible read-window overshoot and leaving STM.
	burstCompletionAllowance = monitorReadWindow + monitorExitRoundTrip + burstCompletionSlack
	// parkedWakePollInterval listens for one second each minute while ordinary
	// parked samples remain ten minutes apart, a roughly 1.7% serial duty cycle.
	parkedWakePollInterval = time.Minute
	// auxVoltageInterval paces the adapter's own supply reading. It answers with
	// the vehicle asleep, which is the whole point of it, so it is the one thing
	// worth asking for on a bus that has gone quiet. Asking often would spend
	// serial time for nothing: a 12V battery does not move quickly.
	auxVoltageInterval = 5 * time.Minute
	// auxVoltageFailureLimit is how many consecutive unanswered readings mean the
	// adapter itself has gone, rather than one reading being lost to a busy bus.
	auxVoltageFailureLimit = 3
	// eventDebounce is the shortest gap between two event-triggered samples. A
	// signal that chatters at frame rate must not turn into an upload storm.
	eventDebounce = 30 * time.Second
	// filterAuditInterval is how often a silent filtered monitor is asked to
	// prove that the silence is the vehicle's and not its own.
	filterAuditInterval = 60 * time.Second
	// filterAuditBurst is how long the unfiltered comparison listens. A vehicle
	// broadcasting at all repeats well inside this.
	filterAuditBurst = 3 * time.Second
	// busWakeQuiet is how long the bus must have been silent for the next frame
	// to count as the vehicle waking rather than as an ordinary gap between
	// broadcasts. A car that is awake repeats within milliseconds, so anything
	// this long means it had stopped.
	busWakeQuiet = time.Minute
	// motionOnsetKMH is the speed at which a decoded reading stops being receiver
	// or sensor noise and becomes a vehicle that has started moving. It matches
	// the threshold the activity detector uses, so the event and the cadence
	// change it triggers agree about what motion is.
	motionOnsetKMH = 3.0
	// consecutiveExitTimeoutLimit is how many stream exits in a row may go
	// unanswered before the adapter counts as wedged. A burst that listened and
	// then waited too long for its prompt has still heard the bus, while the
	// ladder it would otherwise enter costs an ATZ, a re-prepare bounded at 90 s,
	// a reopen and a physical USB reset, and ends by failing the session and
	// retracting the whole CAN channel. One late prompt does not buy that.
	consecutiveExitTimeoutLimit = 3
	// quietSettleMargin is added to the liveness window before a gap in frames is
	// called sleep. A momentary pause between broadcasts is not the ignition
	// going off, and reporting it as one would park a moving car.
	quietSettleMargin = 5 * time.Second
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

var errProfileSessionClosed = errors.New("profile session closed")

type profileBurstCycle struct {
	done   chan struct{}
	window time.Duration
}

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
	lastVoltageAt   time.Time
	voltageFailures int
	attached        bool

	eventValues map[string]any
	eventReason string
	lastEventAt time.Time
	eventGap    time.Duration

	auditInterval    time.Duration
	auditBurst       time.Duration
	fellBack         bool
	contradictions   int
	lastAnyFrame     time.Time
	monitorStartedAt time.Time
	lastSpeed        float64
	lastSpeedSeen    bool
	quietSettle      time.Duration
	busQuiet         bool
	burstWindow      time.Duration
	wakePollInterval time.Duration
	lastBurstRequest time.Time
	burstRequests    chan struct{}
	burstCycle       *profileBurstCycle
	carriedSnapshot  bool
	exitTimeouts     int
	resetUSB         func(string) error

	sessionDone sync.WaitGroup

	stop chan struct{}
}

func NewProfileProvider(adapter *OBDAdapter, decoder *profile.DecoderEngine) *ProfileProvider {
	allowed := make(map[int]struct{})
	for _, canID := range decoder.CANIDs() {
		allowed[canID] = struct{}{}
	}
	return &ProfileProvider{
		adapter: adapter, decoder: decoder, trial: protocolTrial,
		allowed: allowed, observations: model.MetricObservations{},
		voltageInterval: auxVoltageInterval,
		eventGap:        eventDebounce, eventValues: map[string]any{},
		auditInterval: filterAuditInterval, auditBurst: filterAuditBurst,
		quietSettle: protocolTrial + quietSettleMargin,
		burstWindow: profileBurstWindow, wakePollInterval: parkedWakePollInterval,
		burstRequests: make(chan struct{}, 1),
		resetUSB:      func(string) error { return fmt.Errorf("USB reset is not configured") },
	}
}

// ProfileBurstWindow derives the service listen window from its in-use cadence.
func ProfileBurstWindow(samplingInterval time.Duration) time.Duration {
	third := (samplingInterval / 3).Truncate(100 * time.Millisecond)
	return min(max(third, minimumProfileBurstWindow), profileBurstWindow)
}

// SetSamplingInterval keeps the profile burst short enough for the configured
// in-use cadence. Parked wake polls deliberately retain their full one second.
func (provider *ProfileProvider) SetSamplingInterval(samplingInterval time.Duration) {
	provider.mutex.Lock()
	provider.burstWindow = ProfileBurstWindow(samplingInterval)
	provider.mutex.Unlock()
}

// SetUSBRecovery supplies the service's narrowly scoped physical reset. Tests
// replace it to verify escalation without touching host hardware.
func (provider *ProfileProvider) SetUSBRecovery(reset func(string) error) {
	provider.resetUSB = reset
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
	silent := provider.stop != nil && (provider.lastDecoded.IsZero() || provider.busQuiet)
	// The mode is reported whenever one is in force, working or not, because
	// "filtered and hearing nothing" and "unfiltered and hearing nothing" are
	// different problems and the interface cannot tell them apart otherwise.
	if provider.stop != nil {
		parts = append(parts, fmt.Sprintf("listen bursts: %s; sample window %s; wake poll window %s",
			provider.modeDescription(), provider.burstWindow, profileBurstWindow))
	}
	if provider.carriedSnapshot {
		parts = append(parts, "carried observations: requested listen burst did not finish in time")
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

// modeDescription names the monitor in force. The caller holds the mutex.
//
// Filtered is the expected steady state and the only one that keeps up with a
// busy bus: unfiltered monitoring on a live vehicle at the adapter's default
// baud overflows its buffer and drops most of what it sees, so the fallback is
// a last resort and says so rather than reading as an equivalent choice.
func (provider *ProfileProvider) modeDescription() string {
	if !provider.unfiltered {
		return "filtered"
	}
	hazard := "unfiltered fallback (last resort); expect dropped frames on a live bus"
	if provider.fellBack {
		return hazard + "; hardware filters delivered nothing while the bus was live"
	}
	return hazard + "; hardware filters ineffective at startup"
}

// quietDescription says how long the bus has been silent while the monitor is
// still running. A vehicle asleep overnight is the ordinary case, so the reading
// names the duration rather than implying a fault. The caller holds the mutex.
func (provider *ProfileProvider) quietDescription() string {
	if provider.lastFrame.IsZero() {
		return "bus quiet since start"
	}
	quiet := time.Since(provider.lastFrame).Round(time.Second)
	return fmt.Sprintf("bus quiet for %s", quiet)
}

// Live reports whether a frame arrived recently.
//
// The decoded metrics cannot answer this: they are the last known values and are
// republished unchanged after the bus goes quiet, so a parked vehicle looks from
// the metrics alone exactly like a moving one.
func (provider *ProfileProvider) Live() bool {
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	return !provider.lastFrame.IsZero() && !provider.busQuiet && time.Since(provider.lastFrame) < 2*provider.wakePollInterval
}

// ReadObservations asks the session goroutine for the burst belonging to this
// sample. Waiting on its completion rather than the hardware keeps recovery off
// the sampling thread and gives the caller a hard upper bound.
func (provider *ProfileProvider) ReadObservations() (model.MetricObservations, error) {
	cycle, sampleWindow := provider.requestBurst()
	if cycle == nil {
		provider.mutex.Lock()
		provider.carriedSnapshot = true
		observations := copyObservations(provider.observations)
		provider.mutex.Unlock()
		return observations, nil
	}
	timer := time.NewTimer(sampleWindow + burstCompletionAllowance)
	defer timer.Stop()
	completed := false
	select {
	case <-cycle.done:
		completed = true
	case <-timer.C:
	}
	provider.mutex.Lock()
	observations := copyObservations(provider.observations)
	provider.carriedSnapshot = !completed
	provider.mutex.Unlock()
	return observations, nil
}

func (provider *ProfileProvider) requestBurst() (*profileBurstCycle, time.Duration) {
	provider.mutex.Lock()
	provider.lastBurstRequest = time.Now()
	sampleWindow := provider.burstWindow
	if provider.stop == nil {
		provider.mutex.Unlock()
		return nil, sampleWindow
	}
	cycle := provider.burstCycle
	created := cycle == nil
	if created {
		cycle = &profileBurstCycle{done: make(chan struct{}), window: provider.burstWindow}
		provider.burstCycle = cycle
	}
	provider.mutex.Unlock()
	if created {
		select {
		case provider.burstRequests <- struct{}{}:
		default:
		}
	}
	return cycle, sampleWindow
}

// Start connects and begins the burst session. The retrying runtime owner calls it on
// its acquisition goroutine; reads only take snapshots and never touch hardware.
func (provider *ProfileProvider) Start() {
	provider.mutex.Lock()
	running := provider.stop != nil
	if running {
		provider.mutex.Unlock()
		return
	}
	provider.mutex.Unlock()

	if err := provider.adapter.Connect(); err != nil {
		provider.fail(fmt.Sprintf("device %s failed to open: %v", provider.adapter.device, err))
		return
	}
	// Read the supply before the stream starts. It is the one value available with
	// the vehicle asleep, so a bus that never speaks still produces a sample with
	// something true in it from the first collection onwards.
	provider.readVoltage()
	if err := provider.prepare(); err != nil {
		provider.adapter.Close()
		provider.fail(err.Error())
		return
	}

	stop := make(chan struct{})
	provider.mutex.Lock()
	provider.stop = stop
	provider.monitorStartedAt = time.Now().UTC()
	provider.failure = ""
	provider.mutex.Unlock()

	provider.sessionDone.Add(1)
	go provider.runSession(stop)
}
func (provider *ProfileProvider) record(frame model.CANFrame) {
	observedAt := frameTime(frame)
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	provider.noteBusActivity(observedAt)
	if _, ok := provider.allowed[frame.CANID]; !ok {
		return
	}
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
	provider.noteMotionOnset(next, observedAt)
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
	provider.stop = nil
	provider.mutex.Unlock()
	if stop != nil {
		close(stop)
		provider.sessionDone.Wait()
	}
	provider.adapter.Close()
}

func (provider *ProfileProvider) runSession(stop <-chan struct{}) {
	defer provider.sessionDone.Done()
	wake := time.NewTicker(provider.wakePollInterval)
	voltage := time.NewTicker(provider.voltageInterval)
	audit := time.NewTicker(provider.auditInterval)
	defer wake.Stop()
	defer voltage.Stop()
	defer audit.Stop()
	for {
		select {
		case <-stop:
			return
		case <-provider.burstRequests:
			cycle := provider.pendingBurstCycle()
			if cycle == nil {
				continue
			}
			if err := provider.runBurstCycle(cycle, stop); err != nil {
				if errors.Is(err, errProfileSessionClosed) {
					return
				}
				provider.fail("CAN listen burst failed: " + err.Error())
				return
			}
		case <-wake.C:
			provider.mutex.Lock()
			due := time.Since(provider.lastBurstRequest) >= provider.wakePollInterval
			provider.mutex.Unlock()
			if due {
				cycle := provider.ensureBurstCycle(profileBurstWindow)
				if err := provider.runBurstCycle(cycle, stop); err != nil {
					if errors.Is(err, errProfileSessionClosed) {
						return
					}
					provider.fail("CAN wake poll failed: " + err.Error())
					return
				}
			}
		case <-voltage.C:
			provider.readVoltage()
		case <-audit.C:
			provider.runFilterAudit()
		}
	}
}

func (provider *ProfileProvider) pendingBurstCycle() *profileBurstCycle {
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	return provider.burstCycle
}

func (provider *ProfileProvider) ensureBurstCycle(window time.Duration) *profileBurstCycle {
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	if provider.burstCycle == nil {
		provider.burstCycle = &profileBurstCycle{done: make(chan struct{}), window: window}
	}
	return provider.burstCycle
}

func (provider *ProfileProvider) runBurstCycle(cycle *profileBurstCycle, stop <-chan struct{}) error {
	err := provider.runBurstWithRecovery(cycle.window, stop)
	provider.mutex.Lock()
	if provider.burstCycle == cycle {
		provider.burstCycle = nil
	}
	close(cycle.done)
	provider.mutex.Unlock()
	return err
}

func (provider *ProfileProvider) runBurstWithRecovery(window time.Duration, stop <-chan struct{}) error {
	err := provider.runBurstFor(window)
	switch {
	case err == nil:
		provider.noteStreamExit(false)
		return nil
	// A burst that listened and could not get its prompt back has still heard the
	// bus, so it is a burst failure rather than a reason to start the ladder.
	case errors.Is(err, errMonitorExitTimeout) &&
		provider.noteStreamExit(true) < consecutiveExitTimeoutLimit:
		return nil
	}
	provider.noteStreamExit(false)
	if profileSessionStopped(stop) {
		return errProfileSessionClosed
	}
	if err := provider.adapter.Reset(); err == nil {
		if profileSessionStopped(stop) {
			return errProfileSessionClosed
		}
		if err = provider.prepare(); err == nil {
			return nil
		}
	}
	if profileSessionStopped(stop) {
		return errProfileSessionClosed
	}
	provider.adapter.Close()
	if profileSessionStopped(stop) {
		return errProfileSessionClosed
	}
	if err := provider.adapter.Connect(); err == nil {
		if profileSessionStopped(stop) {
			provider.adapter.Close()
			return errProfileSessionClosed
		}
		if err = provider.prepare(); err == nil {
			return nil
		}
	}
	provider.adapter.Close()
	if profileSessionStopped(stop) {
		return errProfileSessionClosed
	}
	// The ladder ends either way, but the reason it ends has to name its last
	// rung: a physical reset that ran and did not help is a different fault, with
	// a different next step for the owner, from one that was skipped because the
	// previous one was too recent to repeat.
	switch err := provider.resetUSB(provider.adapter.device); {
	case err == nil:
		return errors.New("adapter remained unavailable after reset, reopen, and a USB reset")
	case errors.Is(err, usbrecovery.ErrCoolingDown):
		return fmt.Errorf("adapter remained unavailable after reset and reopen, and no USB reset was performed: %w", err)
	default:
		return fmt.Errorf("reset, reopen, and USB recovery failed: %w", err)
	}
}

// noteStreamExit counts unanswered stream exits in a row and returns the run
// length. Any other outcome ends the run: the limit is about an adapter that has
// stopped answering, not about how many late prompts a session has ever seen.
func (provider *ProfileProvider) noteStreamExit(timedOut bool) int {
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	if !timedOut {
		provider.exitTimeouts = 0
		return 0
	}
	provider.exitTimeouts++
	return provider.exitTimeouts
}

func profileSessionStopped(stop <-chan struct{}) bool {
	select {
	case <-stop:
		return true
	default:
		return false
	}
}

func (provider *ProfileProvider) prepare() error {
	preparation, err := PrepareProfileMonitor(
		provider.adapter, provider.decoder.CANIDs(), provider.trial, 0, false, provider.record,
		nil, time.Now().Add(servicePreparationTimeout),
	)
	if err != nil {
		return err
	}
	provider.mutex.Lock()
	provider.unfiltered = preparation.UseUnfiltered
	provider.baseReport = preparationMonitorReport(preparation)
	provider.monitorReport = provider.baseReport
	provider.mutex.Unlock()
	return nil
}

func (provider *ProfileProvider) runBurstFor(window time.Duration) error {
	provider.mutex.Lock()
	unfiltered := provider.unfiltered
	provider.mutex.Unlock()
	trace, err := provider.adapter.InspectMonitor(window, unfiltered, 0, provider.record)
	provider.updateMonitorReport(trace.Report)
	provider.noteQuietOnset(time.Now().UTC())
	return err
}

// readVoltage runs between listen bursts on the session goroutine.
func (provider *ProfileProvider) readVoltage() {
	reading, err := provider.adapter.Voltage()
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

// auditFilters keeps asking whether a silent filtered monitor is silent because
// the vehicle is asleep or because its own filters are dropping everything.
//
// The question cannot be settled once at startup: a service that starts while
// the car sleeps sees both monitors say nothing, which proves neither. Settling
// on the filtered stream then and never revisiting it is how an adapter whose
// STFAP is accepted but applied wrongly goes deaf for the rest of the session
// while its supply reading keeps working perfectly.
func (provider *ProfileProvider) runFilterAudit() {
	provider.mutex.Lock()
	settled := provider.unfiltered || provider.failure != ""
	heard := !provider.lastFrame.IsZero() && time.Since(provider.lastFrame) < provider.auditInterval
	provider.mutex.Unlock()
	// Nothing to prove once the fallback is in force, and nothing to suspect
	// while frames are arriving: the filtered stream is doing its job.
	if settled || heard {
		return
	}

	// Frames seen here are real observations, not just evidence, so they are
	// decoded on the way through. A wake that happens to land inside the burst
	// must not cost the transition that started it.
	relevant := 0
	count := func(frame model.CANFrame) {
		if _, ok := provider.allowed[frame.CANID]; ok {
			relevant++
		}
		provider.record(frame)
	}
	if _, err := provider.adapter.SampleMonitorAll(provider.auditBurst, count); err != nil {
		return
	}
	// Only frames this profile asked for decide it. Unrelated traffic proves the
	// bus is awake, but switching to software filtering would drop those too, so
	// it is not evidence that the fallback would help.
	if relevant == 0 {
		return
	}

	// Reaching here contradicts what this firmware is expected to do: filters
	// that carried thousands of frames per second in verification have now
	// delivered none while the bus was demonstrably live. The switch is made
	// because hearing something badly beats hearing nothing, but it is recorded
	// as the surprise it is rather than as a routine adjustment.
	provider.mutex.Lock()
	provider.unfiltered = true
	provider.fellBack = true
	provider.contradictions++
	provider.mutex.Unlock()
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

// raiseEvent arms one early sample, subject to the shared debounce so a signal
// that chatters at frame rate costs one extra sample rather than thousands. The
// caller holds the mutex.
func (provider *ProfileProvider) raiseEvent(at time.Time, reason string) {
	if !provider.lastEventAt.IsZero() && at.Sub(provider.lastEventAt) < provider.eventGap {
		return
	}
	provider.lastEventAt = at
	provider.eventReason = reason
}

// noteBusActivity turns the first frame after a silence into a wake event.
//
// It is deliberately independent of the profile: a vehicle switched on without
// being driven may flip no metric this profile decodes, and on the C-Zero the
// readiness frame is not even among the identifiers it watches. Traffic itself
// is the evidence that the car came back, and waiting out a ten-minute parked
// cadence to say so is how switching the car on looked like nothing happening.
// The caller holds the mutex.
func (provider *ProfileProvider) noteBusActivity(at time.Time) {
	previous := provider.lastAnyFrame
	provider.lastAnyFrame = at
	provider.busQuiet = false
	quiet := previous
	if quiet.IsZero() {
		// Nothing has been heard yet, so the silence is measured from the moment
		// this monitor began listening. Starting against a car that is already
		// running is not a wake.
		quiet = provider.monitorStartedAt
	}
	if quiet.IsZero() || at.Sub(quiet) < busWakeQuiet {
		return
	}
	provider.raiseEvent(at, fmt.Sprintf("vehicle bus woke after %s quiet", at.Sub(quiet).Round(time.Second)))
}

// watchQuiet notices the bus stopping. Nothing calls in when frames cease, so
// the absence has to be looked for rather than waited on.
// noteQuietOnset turns the bus falling silent into one event.
//
// The sample it triggers carries whatever the drive last decoded — the closing
// state of charge and odometer — together with the new source state, so the
// dashboard shows where the car was left within seconds of the ignition going
// off instead of at the end of a parked cadence. One event per transition: a bus
// that flaps on the edge of sleep sets the flag once and the shared debounce
// covers the rest.
func (provider *ProfileProvider) noteQuietOnset(at time.Time) {
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	if provider.busQuiet || provider.lastAnyFrame.IsZero() {
		return
	}
	quiet := at.Sub(provider.lastAnyFrame)
	if quiet < provider.quietSettle {
		return
	}
	provider.busQuiet = true
	provider.raiseEvent(at, fmt.Sprintf("vehicle bus went quiet after %s", quiet.Round(time.Second)))
}

// noteMotionOnset turns a standing vehicle starting to move into an event.
//
// A state flip cannot cover this: speed is a number, and the car that matters is
// the one whose speed went from nothing to something between two samples. On a
// parked cadence that gap is ten minutes, which is how an entire first leg of a
// journey happened inside one sampling interval and was never recorded at all.
// The caller holds the mutex.
func (provider *ProfileProvider) noteMotionOnset(next model.MetricObservations, at time.Time) {
	observation, present := next["vehicle.speed"]
	if !present {
		return
	}
	speed, ok := numeric(observation.Value)
	if !ok {
		return
	}
	previous, seen := provider.lastSpeed, provider.lastSpeedSeen
	provider.lastSpeed, provider.lastSpeedSeen = speed, true
	if !seen || previous >= motionOnsetKMH || speed < motionOnsetKMH {
		return
	}
	provider.raiseEvent(at, fmt.Sprintf("vehicle started moving at %.0f km/h", speed))
}

func numeric(value any) (float64, bool) {
	switch typed := value.(type) {
	case float64:
		return typed, true
	case float32:
		return float64(typed), true
	case int:
		return float64(typed), true
	case int64:
		return float64(typed), true
	}
	return 0, false
}

// noteEvents records a state change worth reporting before the cadence would.
// Only a change counts. The caller holds the mutex.
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
		provider.raiseEvent(at, fmt.Sprintf("%s changed to %v", key, observation.Value))
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
