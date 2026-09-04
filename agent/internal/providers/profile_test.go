package providers

import (
	"errors"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Buco7854/carhibou/agent/internal/model"
	"github.com/Buco7854/carhibou/agent/internal/profile"
	"go.bug.st/serial"
)

const oneSignal = `{"id":"t","signals":[{"name":"battery.soc","source":{"type":"can","can_id":884},
"decoder":{"byte_offset":1,"data_type":"uint8","scale":0.5,"offset":-5}}]}`

func testDecoder(t *testing.T) *profile.DecoderEngine {
	t.Helper()
	decoder, err := profile.ParseJSON([]byte(oneSignal))
	if err != nil {
		t.Fatal(err)
	}
	return decoder
}

func TestProfileObservationsKeepFrameTimesAndDerivedDependencyAge(t *testing.T) {
	decoder, err := profile.ParseJSON([]byte(`{
        "id":"derived-times",
        "signals":[
          {"name":"battery.pack_voltage","source":{"type":"can","can_id":1},"decoder":{"data_type":"uint8"}},
          {"name":"battery.current","source":{"type":"can","can_id":2},"decoder":{"data_type":"uint8"}}
        ],
        "computed_metrics":[{"name":"battery.power","operation":"multiply","inputs":["battery.pack_voltage","battery.current"]}]
    }`))
	if err != nil {
		t.Fatal(err)
	}
	provider := NewProfileProvider(NewOBDAdapter("/dev/carhibou-absent"), decoder)
	old := time.Date(2026, 8, 29, 1, 0, 0, 0, time.UTC)
	newer := old.Add(10 * time.Second)
	newest := old.Add(20 * time.Second)
	provider.record(model.CANFrame{Timestamp: float64(old.Unix()), CANID: 1, Data: []byte{10}})
	provider.record(model.CANFrame{Timestamp: float64(newer.Unix()), CANID: 2, Data: []byte{3}})
	provider.record(model.CANFrame{Timestamp: float64(newest.Unix()), CANID: 2, Data: []byte{4}})

	observations := provider.observations
	if got := observations["battery.pack_voltage"].Metadata.ObservedAt; !got.Equal(old) {
		t.Fatalf("voltage observed_at=%s want %s", got, old)
	}
	if got := observations["battery.current"].Metadata.ObservedAt; !got.Equal(newest) {
		t.Fatalf("current observed_at=%s want %s", got, newest)
	}
	power := observations["battery.power"]
	if power.Metadata.Method != model.MethodDerived || !power.Metadata.ObservedAt.Equal(old) {
		t.Fatalf("derived power metadata=%#v, want oldest dependency %s", power.Metadata, old)
	}
	if power.Value != float64(40) {
		t.Fatalf("derived power=%v want 40", power.Value)
	}
}

func TestProfileStartsMonitoringAndRetainsFramesBeforeTheFirstRead(t *testing.T) {
	port := &scriptedPort{replies: map[string]string{
		"ATZ":    "OK\r>",
		"ATE0":   "OK\r>",
		"ATL0":   "OK\r>",
		"ATS1":   "OK\r>",
		"ATH1":   "OK\r>",
		"STBRT":  "?\r>",
		"STFAP":  "OK\r>",
		"ATSP6":  "OK\r>",
		"ATCAF0": "OK\r>",
		"STM":    "374 8 00 90 00 00 00 00 00 00\r",
		"\r":     "STOPPED\r>",
	}}
	previousOpen := openOBDPort
	openOBDPort = func(string, *serial.Mode) (serial.Port, error) { return port, nil }
	t.Cleanup(func() { openOBDPort = previousOpen })

	provider := NewProfileProvider(NewOBDAdapter("scripted"), testDecoder(t))
	provider.trial = 25 * time.Millisecond
	defer provider.Close()
	provider.Start()

	provider.mutex.Lock()
	running := provider.stop != nil
	provider.mutex.Unlock()
	if !running {
		t.Fatal("profile monitor was not running when Start returned")
	}
	observations, err := provider.ReadObservations()
	if err != nil {
		t.Fatal(err)
	}
	if got := observations["battery.soc"].Value; got != float64(67) {
		t.Fatalf("first battery.soc=%v, want decoded frame captured during Start", got)
	}
}

func TestProfileFallsBackWhenFilteredSTMIsSilentButSTMAWorks(t *testing.T) {
	port := &profilePipelinePort{protocolFrame: true, unfilteredFrame: true}
	previousOpen := openOBDPort
	openOBDPort = func(string, *serial.Mode) (serial.Port, error) { return port, nil }
	t.Cleanup(func() { openOBDPort = previousOpen })

	provider := NewProfileProvider(NewOBDAdapter("scripted"), testDecoder(t))
	provider.trial = 20 * time.Millisecond
	defer provider.Close()
	provider.Start()

	if !provider.unfiltered {
		t.Fatal("filtered silence with working STMA did not enable the unfiltered fallback")
	}
	if state := provider.State(); !strings.Contains(state, "hardware filters ineffective") {
		t.Fatalf("state=%q, want the degraded monitor named", state)
	}
	observations, err := provider.ReadObservations()
	if err != nil {
		t.Fatal(err)
	}
	if got := observations["battery.soc"].Value; got != float64(67) {
		t.Fatalf("battery.soc=%v, want the STMA frame decoded", got)
	}

	// Select, filter, then listen. Filters have to be installed before any trial
	// listens: on this firmware a filtered monitor with no filters installed
	// passes nothing, so a trial that listened first could only ever report
	// silence, however loudly the bus was talking.
	recorded := port.recordedCommands()
	protocolIndex := commandIndex(recorded, "ATSP6", 0)
	filterIndex := commandIndex(recorded, "STFAP 374,FFF", 0)
	firstSTM := commandIndex(recorded, "STM", 0)
	filteredSTM := commandIndex(recorded, "STM", firstSTM+1)
	stma := commandIndex(recorded, "STMA", 0)
	if protocolIndex < 0 || filterIndex < 0 || firstSTM < 0 || filteredSTM < 0 || stma < 0 {
		t.Fatalf("command order=%v, want protocol, filters, filtered STM, then STMA", recorded)
	}
	if !(protocolIndex < filterIndex && filterIndex < firstSTM && firstSTM < filteredSTM && filteredSTM < stma) {
		t.Fatalf("command order=%v, want protocol, filters, filtered STM, then STMA", recorded)
	}
}

func TestProfileMonitorPreparationReportsTheServicePipeline(t *testing.T) {
	port := &profilePipelinePort{protocolFrame: true, unfilteredFrame: true}
	adapter := NewOBDAdapter("scripted")
	adapter.port = port
	adapter.CommandWindow = time.Second

	stages := []string{}
	preparation, err := PrepareProfileMonitor(
		adapter, []int{0x374}, 15*time.Millisecond, 10, true, func(model.CANFrame) {},
		func(stage string) { stages = append(stages, stage) }, time.Time{},
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(stages) == 0 {
		t.Fatal("preparation reported no progress; the diagnostic reads as a hang")
	}
	if len(preparation.ProtocolTrials) != 1 || preparation.ProtocolTrials[0].Trace.Report.ParsedFrames != 1 {
		t.Fatalf("protocol trials=%+v", preparation.ProtocolTrials)
	}
	if len(preparation.FilterCommands) != 1 || preparation.FilterCommands[0].Command != "STFAP 374,FFF" ||
		len(preparation.FilterCommands[0].Response) != 1 || preparation.FilterCommands[0].Response[0] != "OK" {
		t.Fatalf("filter commands=%+v", preparation.FilterCommands)
	}
	if preparation.Filtered.Report.ParsedFrames != 0 || len(preparation.Filtered.RawLines) != 1 {
		t.Fatalf("filtered trace=%+v", preparation.Filtered)
	}
	if preparation.Unfiltered == nil || preparation.Unfiltered.Report.ParsedFrames != 1 || len(preparation.Unfiltered.RawLines) != 2 {
		t.Fatalf("unfiltered trace=%+v", preparation.Unfiltered)
	}
}

// A diagnostic that cannot finish must say what it managed rather than run on
// past any useful bound.
func TestPreparationStopsAtItsDeadlineAndKeepsWhatItRan(t *testing.T) {
	port := &profilePipelinePort{}
	previousOpen := openOBDPort
	openOBDPort = func(string, *serial.Mode) (serial.Port, error) { return port, nil }
	t.Cleanup(func() { openOBDPort = previousOpen })

	adapter := NewOBDAdapter("scripted")
	if err := adapter.Connect(); err != nil {
		t.Fatal(err)
	}
	defer adapter.Close()
	adapter.CommandWindow = time.Second

	preparation, err := PrepareProfileMonitor(
		adapter, []int{0x374}, 15*time.Millisecond, 10, true, func(model.CANFrame) {},
		nil, time.Now().Add(-time.Second),
	)
	if !errors.Is(err, ErrPreparationDeadline) {
		t.Fatalf("err=%v, want %v", err, ErrPreparationDeadline)
	}
	if preparation.InitialBaud == 0 {
		t.Fatal("partial preparation should still carry what it observed")
	}
}

func TestNegotiatedBaudRequiresSustainedCleanCAN(t *testing.T) {
	if sustainedCleanTraffic([]ProtocolTrialResult{{Trace: MonitorTrace{Report: MonitorReport{ParsedFrames: 2}}}}) {
		t.Fatal("two frames were accepted as sustained traffic")
	}
	if !sustainedCleanTraffic([]ProtocolTrialResult{{Trace: MonitorTrace{Report: MonitorReport{ParsedFrames: 3}}}}) {
		t.Fatal("three clean frames were rejected")
	}
	if sustainedCleanTraffic([]ProtocolTrialResult{{Trace: MonitorTrace{Report: MonitorReport{
		ParsedFrames: 3, MalformedFrames: 1, DroppedData: true,
	}}}}) {
		t.Fatal("malformed traffic was accepted as a clean baud verification")
	}
}

func TestProfileNamesAQuietMonitorInEveryStateReading(t *testing.T) {
	port := &profilePipelinePort{}
	previousOpen := openOBDPort
	openOBDPort = func(string, *serial.Mode) (serial.Port, error) { return port, nil }
	t.Cleanup(func() { openOBDPort = previousOpen })

	provider := NewProfileProvider(NewOBDAdapter("scripted"), testDecoder(t))
	provider.trial = 10 * time.Millisecond
	defer provider.Close()
	provider.Start()
	if state := provider.State(); !strings.Contains(state, "bus quiet") {
		t.Fatalf("quiet monitor state=%q", state)
	}
}

// A bus that has gone quiet is the ordinary overnight case, not a fault: the
// adapter is still answering and the vehicle is simply asleep. Reporting that as
// a dead channel is what retracted a parked car's odometer every night.
func TestQuietBusKeepsTheProviderAttachedAndFailureFree(t *testing.T) {
	port := &profilePipelinePort{}
	previousOpen := openOBDPort
	openOBDPort = func(string, *serial.Mode) (serial.Port, error) { return port, nil }
	t.Cleanup(func() { openOBDPort = previousOpen })

	provider := NewProfileProvider(NewOBDAdapter("scripted"), testDecoder(t))
	provider.trial = 10 * time.Millisecond
	defer provider.Close()
	provider.Start()

	if provider.Live() {
		t.Fatal("a silent bus should not read as live")
	}
	if !provider.Attached() {
		t.Fatal("a silent bus must leave the adapter attached")
	}
	if status := provider.Status(); status != "" {
		t.Fatalf("quiet bus reported a failure: %q", status)
	}
}

// The adapter refusing to answer its own supply reading is the other case: the
// hardware is gone, so the values it decoded stop being observations.
func TestUnansweredSupplyReadingsDetachTheProvider(t *testing.T) {
	provider := NewProfileProvider(NewOBDAdapter("scripted"), testDecoder(t))
	for attempt := 0; attempt < auxVoltageFailureLimit-1; attempt++ {
		provider.recordVoltageFailure()
		if !provider.Attached() {
			t.Fatalf("detached after %d failures, want %d", attempt+1, auxVoltageFailureLimit)
		}
	}
	provider.recordVoltageFailure()
	if provider.Attached() {
		t.Fatal("adapter that stopped answering must read as detached")
	}
	if status := provider.Status(); status == "" {
		t.Fatal("a detached adapter must say why it published nothing")
	}
}

// The supply is the one reading available with the vehicle asleep, so it is
// published as an ordinary observation on the adapter's own channel.
func TestSupplyReadingIsPublishedAsAnAuxVoltageObservation(t *testing.T) {
	provider := NewProfileProvider(NewOBDAdapter("scripted"), testDecoder(t))
	provider.storeVoltage(12.4)
	observations, err := provider.ReadObservations()
	if err != nil {
		t.Fatal(err)
	}
	observation, present := observations[AuxVoltageMetric]
	if !present {
		t.Fatalf("no %s in %#v", AuxVoltageMetric, observations)
	}
	if observation.Value != 12.4 {
		t.Fatalf("value=%v, want 12.4", observation.Value)
	}
	if observation.Metadata.Channel != model.ChannelOBD {
		t.Fatalf("channel=%q, want %q", observation.Metadata.Channel, model.ChannelOBD)
	}
	if observation.Metadata.Method != model.MethodDirect {
		t.Fatalf("method=%q, want %q", observation.Metadata.Method, model.MethodDirect)
	}
}

// A state flip is news the cadence should not sit on, but a signal that chatters
// at frame rate must cost one extra sample rather than thousands.
func TestStateChangesRaiseOneDebouncedEvent(t *testing.T) {
	provider := NewProfileProvider(NewOBDAdapter("scripted"), testDecoder(t))
	at := time.Now().UTC()
	charging := func(value any) model.MetricObservations {
		return model.MetricObservations{
			"charging.active": {Value: value, Metadata: model.ObservationMetadata{ObservedAt: at}},
		}
	}
	provider.noteEvents(charging(false), at)
	if reason := provider.TakeEvent(); reason != "" {
		t.Fatalf("first sighting raised an event: %q", reason)
	}
	provider.noteEvents(charging(true), at)
	reason := provider.TakeEvent()
	if !strings.Contains(reason, "charging.active") {
		t.Fatalf("reason=%q, want the changed metric named", reason)
	}
	if second := provider.TakeEvent(); second != "" {
		t.Fatalf("event survived being taken: %q", second)
	}
	provider.noteEvents(charging(false), at.Add(time.Second))
	if reason := provider.TakeEvent(); reason != "" {
		t.Fatalf("a chattering signal raised a second event inside the debounce: %q", reason)
	}
	provider.noteEvents(charging(true), at.Add(2*eventDebounce))
	if reason := provider.TakeEvent(); reason == "" {
		t.Fatal("a change after the debounce window should raise an event")
	}
}

// Sampling must not wait for the bus. Frames arrive continuously whether or not
// anyone is reading, and a window opened per sample both blocked for its whole
// duration — making a one-second cadence impossible — and saw only the fraction
// of the bus that fell inside it.
func TestReadMetricsDoesNotWaitForTheBus(t *testing.T) {
	adapter := NewOBDAdapter("never-answering")
	adapter.port = &silentPort{}
	provider := NewProfileProvider(adapter, testDecoder(t))
	defer provider.Close()

	started := time.Now()
	for i := 0; i < 3; i++ {
		if _, err := provider.ReadObservations(); err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
	}
	if elapsed := time.Since(started); elapsed > 100*time.Millisecond {
		t.Fatalf("three samples took %s; sampling is waiting on the bus", elapsed)
	}
	if provider.Live() {
		t.Fatal("a provider that never saw a frame is not live")
	}
}

// Closing must be safe whether or not a monitor ever started, because an agent
// shuts down the same way after a good run and after a failed connection.
func TestClosingIsSafeWithoutAMonitor(t *testing.T) {
	provider := NewProfileProvider(NewOBDAdapter("/dev/carhibou-absent"), testDecoder(t))
	provider.Close()
	provider.Close()
}

type profilePipelinePort struct {
	scriptedPort
	// The monitor writes from its own goroutine while the test reads the command
	// log, so the log is guarded. Without this the race detector fails the whole
	// package on a fixture rather than on anything the agent does.
	mutex           sync.Mutex
	commands        []string
	stmCount        int
	protocolFrame   bool
	filteredFrame   bool
	unfilteredFrame bool
}

// recordedCommands is the only safe way to read the log while a monitor runs.
func (port *profilePipelinePort) recordedCommands() []string {
	port.mutex.Lock()
	defer port.mutex.Unlock()
	return append([]string(nil), port.commands...)
}

func (port *profilePipelinePort) Write(payload []byte) (int, error) {
	command := strings.TrimSuffix(string(payload), "\r")
	port.mutex.Lock()
	port.commands = append(port.commands, command)
	port.mutex.Unlock()
	switch {
	case command == "STBRT 500":
		port.pending = "?\r>"
	case command == "STM":
		port.stmCount++
		if (port.stmCount == 1 && port.protocolFrame) || (port.stmCount > 1 && port.filteredFrame) {
			port.pending = "374 8 00 90 00 00 00 00 00 00\r"
		} else {
			port.pending = ""
		}
	case command == "STMA":
		if port.unfilteredFrame {
			port.pending = "374 8 00 90 00 00 00 00 00 00\r"
		} else {
			port.pending = ""
		}
	case command == "":
		port.pending = "STOPPED\r>"
	default:
		port.pending = "OK\r>"
	}
	return len(payload), nil
}

func commandIndex(commands []string, target string, start int) int {
	for index := start; index < len(commands); index++ {
		if commands[index] == target {
			return index
		}
	}
	return -1
}
