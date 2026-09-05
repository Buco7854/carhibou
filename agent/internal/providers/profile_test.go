package providers

import (
	"errors"
	"fmt"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Buco7854/carhibou/agent/internal/model"
	"github.com/Buco7854/carhibou/agent/internal/profile"
	"github.com/Buco7854/carhibou/agent/internal/usbrecovery"
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

// Selecting a protocol can clear CAN auto formatting on an STN adapter, so
// disabling it first is silently undone and the monitor spends the session
// waiting for ISO 15765 messages on a bus that broadcasts raw CAN.
func TestPreparationDisablesCANFormattingAfterSelectingAndFiltering(t *testing.T) {
	port := &profilePipelinePort{protocolFrame: true, filteredFrame: true}
	previousOpen := openOBDPort
	openOBDPort = func(string, *serial.Mode) (serial.Port, error) { return port, nil }
	t.Cleanup(func() { openOBDPort = previousOpen })
	adapter := NewOBDAdapter("scripted")
	adapter.CommandWindow = 100 * time.Millisecond
	if err := adapter.Connect(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(adapter.Close)
	before := len(port.recordedCommands())

	preparation, err := PrepareProfileMonitor(
		adapter, []int{884}, 10*time.Millisecond, 0, false, func(model.CANFrame) {}, nil, time.Time{},
	)
	if err != nil {
		t.Fatal(err)
	}
	commands := port.recordedCommands()[before:]
	selected := commandIndex(commands, "ATSP6", 0)
	filtered := commandIndex(commands, "STFAP 374,FFF", 0)
	raw := commandIndex(commands, "ATCAF0", 0)
	listened := commandIndex(commands, "STM", 0)
	if selected < 0 || filtered < 0 || raw < 0 || listened < 0 {
		t.Fatalf("commands=%v, want a select, a filter, ATCAF0 and a listen", commands)
	}
	if selected > filtered || filtered > raw || raw > listened {
		t.Fatalf("ATSP=%d STFAP=%d ATCAF0=%d STM=%d, want select, filter, disable formatting, listen",
			selected, filtered, raw, listened)
	}
	if preparation.FramesAfterRawCAN == 0 {
		t.Fatal("preparation parsed no frames after the raw-CAN ordering it reports")
	}
}

func TestProfileBurstUsesPreparedRawCANAndStopsWithinItsBound(t *testing.T) {
	port := &profilePipelinePort{protocolFrame: true, filteredFrame: true}
	previousOpen := openOBDPort
	openOBDPort = func(string, *serial.Mode) (serial.Port, error) { return port, nil }
	t.Cleanup(func() { openOBDPort = previousOpen })
	provider := NewProfileProvider(NewOBDAdapter("scripted"), testDecoder(t))
	provider.trial = 10 * time.Millisecond
	provider.burstWindow = 25 * time.Millisecond
	provider.wakePollInterval = time.Hour
	provider.auditInterval = time.Hour
	defer provider.Close()
	provider.Start()
	preparedCommands := port.recordedCommands()
	preparedCAF := countCommand(preparedCommands, "ATCAF0")

	started := time.Now()
	if _, err := provider.ReadObservations(); err != nil {
		t.Fatal(err)
	}
	if elapsed := time.Since(started); elapsed < provider.burstWindow || elapsed > provider.burstWindow+burstCompletionAllowance {
		t.Fatalf("burst duration=%s, want %s..%s", elapsed, provider.burstWindow, provider.burstWindow+burstCompletionAllowance)
	}
	before := port.recordedCommands()
	if got := countCommand(before, "ATCAF0"); got != preparedCAF {
		t.Fatalf("ATCAF0 count=%d after sample, want preparation-only count %d", got, preparedCAF)
	}
	time.Sleep(2 * provider.burstWindow)
	after := port.recordedCommands()
	// A cycle ends with the stream exit and the supply reading it carries, and
	// then the line goes quiet until the next sample asks for one.
	if len(after) != len(before) || after[len(after)-1] != "ATRV" {
		t.Fatalf("commands continued after burst: before=%v after=%v", before, after)
	}
	if provider.observations["battery.soc"].Value != float64(67) {
		t.Fatalf("burst observations=%#v", provider.observations)
	}
}

func TestReadObservationsReturnsFramesFromItsOwnBurst(t *testing.T) {
	port := &profilePipelinePort{protocolFrame: true, filteredFrame: true}
	previousOpen := openOBDPort
	openOBDPort = func(string, *serial.Mode) (serial.Port, error) { return port, nil }
	t.Cleanup(func() { openOBDPort = previousOpen })
	provider := NewProfileProvider(NewOBDAdapter("scripted"), testDecoder(t))
	provider.trial = 10 * time.Millisecond
	provider.burstWindow = 25 * time.Millisecond
	provider.wakePollInterval = time.Hour
	provider.auditInterval = time.Hour
	defer provider.Close()
	provider.Start()

	provider.mutex.Lock()
	provider.observations = model.MetricObservations{}
	provider.mutex.Unlock()
	observations, err := provider.ReadObservations()
	if err != nil {
		t.Fatal(err)
	}
	if got := observations["battery.soc"].Value; got != float64(67) {
		t.Fatalf("battery.soc=%v, want the frame decoded by this sample's burst", got)
	}
}

func TestWakePollAndSampleShareOneBurst(t *testing.T) {
	port := &profilePipelinePort{protocolFrame: true, filteredFrame: true}
	previousOpen := openOBDPort
	openOBDPort = func(string, *serial.Mode) (serial.Port, error) { return port, nil }
	t.Cleanup(func() { openOBDPort = previousOpen })
	provider := NewProfileProvider(NewOBDAdapter("scripted"), testDecoder(t))
	provider.trial = 10 * time.Millisecond
	provider.burstWindow = 100 * time.Millisecond
	provider.wakePollInterval = 500 * time.Millisecond
	provider.auditInterval = time.Hour
	defer provider.Close()
	provider.Start()
	baseline := countCommand(port.recordedCommands(), "STM")

	waitFor(t, "the wake poll burst to start", func() bool {
		return countCommand(port.recordedCommands(), "STM") > baseline
	})
	if _, err := provider.ReadObservations(); err != nil {
		t.Fatal(err)
	}
	if got := countCommand(port.recordedCommands(), "STM") - baseline; got != 1 {
		t.Fatalf("listen bursts=%d, want the sample to join the wake poll", got)
	}
}

func TestWakePollRaisesEventAfterAQuietBurst(t *testing.T) {
	port := &wakeablePort{awake: true, filtersWork: true}
	provider := auditProvider(t, port)
	provider.wakePollInterval = time.Hour
	provider.auditInterval = time.Hour
	provider.burstWindow = 20 * time.Millisecond
	provider.Start()
	provider.TakeEvent()

	port.setBus(false, true)
	provider.mutex.Lock()
	provider.lastAnyFrame = time.Now().Add(-time.Minute)
	provider.mutex.Unlock()
	if _, err := provider.ReadObservations(); err != nil {
		t.Fatal(err)
	}
	if reason := provider.TakeEvent(); !strings.Contains(reason, "quiet") {
		t.Fatalf("quiet event=%q", reason)
	}
	provider.mutex.Lock()
	provider.lastEventAt = time.Now().Add(-2 * eventDebounce)
	provider.mutex.Unlock()
	port.setBus(true, true)
	if _, err := provider.ReadObservations(); err != nil {
		t.Fatal(err)
	}
	if reason := provider.TakeEvent(); !strings.Contains(reason, "woke") {
		t.Fatalf("wake event=%q", reason)
	}
}

type escalationPort struct {
	profilePipelinePort
	mute bool
}

func (port *escalationPort) Write(payload []byte) (int, error) {
	count, err := port.profilePipelinePort.Write(payload)
	if port.mute {
		port.scriptedPort.pending = ""
	}
	return count, err
}

func (port *escalationPort) Read(buffer []byte) (int, error) {
	if port.mute {
		time.Sleep(time.Millisecond)
		return 0, nil
	}
	return port.profilePipelinePort.Read(buffer)
}

func TestBurstFailureEscalatesResetReopenThenUSB(t *testing.T) {
	port := &escalationPort{profilePipelinePort: profilePipelinePort{protocolFrame: true, filteredFrame: true}}
	opens := 0
	previousOpen := openOBDPort
	openOBDPort = func(string, *serial.Mode) (serial.Port, error) {
		opens++
		return port, nil
	}
	t.Cleanup(func() { openOBDPort = previousOpen })
	provider := NewProfileProvider(NewOBDAdapter("scripted"), testDecoder(t))
	provider.trial = 5 * time.Millisecond
	provider.burstWindow = 5 * time.Millisecond
	provider.adapter.CommandWindow = 10 * time.Millisecond
	provider.wakePollInterval = time.Hour
	provider.auditInterval = time.Hour
	var usbCalls atomic.Int32
	provider.SetUSBRecovery(func(device string) error {
		usbCalls.Add(1)
		if opens < 2 {
			t.Fatal("USB reset ran before reopen")
		}
		return errors.New("reset unavailable in test")
	})
	defer provider.Close()
	provider.Start()
	commandsBefore := len(port.recordedCommands())
	port.mute = true

	// An adapter that has gone quiet is heard as a run of unanswered stream
	// exits, so the ladder is what a repeated failure escalates to, not one.
	for burst := 0; burst < consecutiveExitTimeoutLimit; burst++ {
		if _, err := provider.ReadObservations(); err != nil {
			t.Fatal(err)
		}
	}
	waitFor(t, "the session recovery ladder to reach USB", func() bool { return usbCalls.Load() == 1 })
	commands := port.recordedCommands()[commandsBefore:]
	if commandIndex(commands, "ATZ", 0) < 0 {
		t.Fatalf("commands=%v, want ATZ before reopen", commands)
	}
	if opens < 2 || usbCalls.Load() != 1 {
		t.Fatalf("opens=%d usb resets=%d, want reopen then one reset", opens, usbCalls.Load())
	}
}

// latePromptPort streams continuously and takes its time returning to the
// command prompt after a monitor stops, which is what a real adapter does while
// it is still draining a busy bus. promptNever is the wedged case, where the
// prompt never comes back at all.
type latePromptPort struct {
	profilePipelinePort
	promptDelay time.Duration
	// voltageDelay holds the supply reply back, which is the one command a burst
	// cycle runs after its stream has already exited.
	voltageDelay time.Duration
	// wedged is set after preparation, so a port that never returns its prompt
	// still gets the session started before the bursts have to cope with it.
	wedged atomic.Bool
	// silent is the adapter that answers nothing at all: a monitor that neither
	// delivers frames nor comes back to its prompt.
	silent    bool
	streaming bool
	held      string
	promptAt  time.Time
	exits     atomic.Int32
}

func (port *latePromptPort) Write(payload []byte) (int, error) {
	command := strings.TrimSuffix(string(payload), "\r")
	count, err := port.profilePipelinePort.Write(payload)
	switch command {
	case "STM", "STMA":
		port.streaming = true
	case "ATRV":
		port.held, port.pending = port.pending, ""
		port.promptAt = time.Now().Add(port.voltageDelay)
	case "":
		port.streaming = false
		port.exits.Add(1)
		port.held, port.pending = port.pending, ""
		port.promptAt = time.Now().Add(port.promptDelay)
		if port.wedged.Load() {
			port.held = ""
		}
	}
	return count, err
}

func (port *latePromptPort) Read(buffer []byte) (int, error) {
	if port.held != "" {
		if time.Now().Before(port.promptAt) {
			time.Sleep(5 * time.Millisecond)
			return 0, nil
		}
		port.pending, port.held = port.held, ""
	}
	if port.streaming && !port.silent && port.pending == "" {
		port.pending = "374 8 00 90 00 00 00 00 00 00\r"
	}
	return port.profilePipelinePort.Read(buffer)
}

func latePromptProvider(t *testing.T, port *latePromptPort) *ProfileProvider {
	t.Helper()
	previousOpen := openOBDPort
	openOBDPort = func(string, *serial.Mode) (serial.Port, error) { return port, nil }
	t.Cleanup(func() { openOBDPort = previousOpen })
	provider := NewProfileProvider(NewOBDAdapter("scripted"), testDecoder(t))
	provider.trial = 5 * time.Millisecond
	provider.burstWindow = 20 * time.Millisecond
	provider.wakePollInterval = time.Hour
	provider.auditInterval = time.Hour
	t.Cleanup(provider.Close)
	return provider
}

// A preparation stage that collected its frames and then waited too long for the
// prompt has proved what it was asked to prove. Failing on that cost the whole
// acquisition — backoff, and the CAN channel retracted — over one slow reply on
// a live bus, while the service bursts the same preparation feeds tolerate three
// unanswered exits in a row.
func TestPreparationKeepsAStageThatHeardFramesBeforeALateExit(t *testing.T) {
	prepare := func(t *testing.T, port *latePromptPort) (ProfileMonitorPreparation, error) {
		t.Helper()
		previousOpen := openOBDPort
		openOBDPort = func(string, *serial.Mode) (serial.Port, error) { return port, nil }
		t.Cleanup(func() { openOBDPort = previousOpen })
		adapter := NewOBDAdapter("scripted")
		if err := adapter.Connect(); err != nil {
			t.Fatal(err)
		}
		t.Cleanup(adapter.Close)
		adapter.CommandWindow = 60 * time.Millisecond
		port.wedged.Store(true)
		// inspectUnfiltered reaches the STMA window, which is the exit with the
		// most buffered traffic behind it and the one the reviewer tripped.
		return PrepareProfileMonitor(
			adapter, []int{884}, 10*time.Millisecond, 0, true, func(model.CANFrame) {}, nil, time.Time{},
		)
	}

	t.Run("frames heard", func(t *testing.T) {
		port := &latePromptPort{profilePipelinePort: profilePipelinePort{protocolFrame: true, filteredFrame: true}}
		preparation, err := prepare(t, port)
		if err != nil {
			t.Fatalf("preparation failed on a late prompt: %v", err)
		}
		if !preparation.HardwareFilterGood || preparation.FramesAfterRawCAN == 0 {
			t.Fatalf("preparation kept no evidence: %+v", preparation)
		}
		if preparation.ProtocolTrials[0].Error == "" {
			t.Fatal("the late prompt was not recorded on the trial that survived it")
		}
	})

	t.Run("nothing heard", func(t *testing.T) {
		port := &latePromptPort{profilePipelinePort: profilePipelinePort{}, silent: true}
		if _, err := prepare(t, port); !errors.Is(err, errMonitorExitTimeout) {
			t.Fatalf("a stage with no frames and no prompt was accepted: %v", err)
		}
	})
}

// The 12 V reading does not depend on the car's bus and doubles as proof the
// adapter is still answering, so every sample measures its own rather than
// republishing whatever a five-minute timer last left behind.
func TestEverySampleCarriesASupplyReadingFromItsOwnBurst(t *testing.T) {
	port := &profilePipelinePort{protocolFrame: true, filteredFrame: true}
	previousOpen := openOBDPort
	openOBDPort = func(string, *serial.Mode) (serial.Port, error) { return port, nil }
	t.Cleanup(func() { openOBDPort = previousOpen })
	provider := NewProfileProvider(NewOBDAdapter("scripted"), testDecoder(t))
	provider.trial = 5 * time.Millisecond
	provider.burstWindow = 20 * time.Millisecond
	provider.wakePollInterval = time.Hour
	provider.auditInterval = time.Hour
	t.Cleanup(provider.Close)
	provider.Start()

	for sample := 1; sample <= 2; sample++ {
		requested := time.Now().UTC()
		observations, err := provider.ReadObservations()
		if err != nil {
			t.Fatal(err)
		}
		supply, present := observations[AuxVoltageMetric]
		if !present {
			t.Fatalf("sample %d carried no %s: %#v", sample, AuxVoltageMetric, observations)
		}
		if supply.Value != 12.4 || supply.Metadata.Channel != model.ChannelOBD {
			t.Fatalf("sample %d supply=%#v", sample, supply)
		}
		if supply.Metadata.ObservedAt.Before(requested) {
			t.Fatalf("sample %d carried a reading from %s, taken before the sample asked at %s",
				sample, supply.Metadata.ObservedAt, requested)
		}
	}
}

// A parked sample is ten minutes apart, so without this it would report a supply
// reading up to ten minutes old. The wake poll runs every minute and takes one.
func TestWakePollRefreshesTheSupplyReading(t *testing.T) {
	port := &profilePipelinePort{protocolFrame: true, filteredFrame: true}
	previousOpen := openOBDPort
	openOBDPort = func(string, *serial.Mode) (serial.Port, error) { return port, nil }
	t.Cleanup(func() { openOBDPort = previousOpen })
	provider := NewProfileProvider(NewOBDAdapter("scripted"), testDecoder(t))
	provider.trial = 5 * time.Millisecond
	provider.burstWindow = 20 * time.Millisecond
	provider.wakePollInterval = 50 * time.Millisecond
	provider.auditInterval = time.Hour
	t.Cleanup(provider.Close)
	provider.Start()
	atStart := provider.supplyReadingTime()

	waitFor(t, "a wake poll to take its own supply reading", func() bool {
		return provider.supplyReadingTime().After(atStart)
	})
}

// The reading runs inside the cycle the sample waits on, so an adapter slow to
// answer it must time the waiter out into the carried snapshot rather than hold
// the sampling thread past the bound.
func TestSlowSupplyReadingStillLeavesTheSampleBounded(t *testing.T) {
	port := &latePromptPort{
		profilePipelinePort: profilePipelinePort{protocolFrame: true, filteredFrame: true},
		voltageDelay:        1200 * time.Millisecond,
	}
	provider := latePromptProvider(t, port)
	provider.Start()

	started := time.Now()
	observations, err := provider.ReadObservations()
	elapsed := time.Since(started)
	if err != nil {
		t.Fatal(err)
	}
	bound := provider.burstWindow + burstCompletionAllowance
	if elapsed < bound || elapsed > bound+150*time.Millisecond {
		t.Fatalf("slow supply reading took %s, want %s..%s", elapsed, bound, bound+150*time.Millisecond)
	}
	if got := observations["battery.soc"].Value; got != float64(67) {
		t.Fatalf("carried battery.soc=%v, want 67", got)
	}
	if state := provider.State(); !strings.Contains(state, "carried observations") {
		t.Fatalf("state=%q, want the carried reading disclosed", state)
	}
}

// A prompt that comes back a third of a second later is a busy adapter, not a
// wedged one. The exit keeps the adapter's own command window, so no number of
// slow-but-answered exits reaches the recovery ladder.
func TestSlowStreamExitNeverReachesTheRecoveryLadder(t *testing.T) {
	port := &latePromptPort{
		profilePipelinePort: profilePipelinePort{protocolFrame: true, filteredFrame: true},
		promptDelay:         350 * time.Millisecond,
	}
	provider := latePromptProvider(t, port)
	provider.SetUSBRecovery(func(string) error {
		t.Error("a slow stream exit reached the USB reset")
		return nil
	})
	provider.Start()
	resets := countCommand(port.recordedCommands(), "ATZ")

	for burst := 1; burst <= consecutiveExitTimeoutLimit; burst++ {
		if _, err := provider.ReadObservations(); err != nil {
			t.Fatal(err)
		}
		if state := provider.State(); strings.Contains(state, "carried") {
			t.Fatalf("burst %d missed its bound: %s", burst, state)
		}
		if got := countCommand(port.recordedCommands(), "ATZ"); got != resets {
			t.Fatalf("burst %d sent %d ATZ, want the %d it started with", burst, got, resets)
		}
		if status := provider.Status(); status != "" {
			t.Fatalf("burst %d failed the session: %s", burst, status)
		}
	}
	if got := port.exits.Load(); got < int32(consecutiveExitTimeoutLimit) {
		t.Fatalf("stream exits=%d, want one per burst", got)
	}
}

// An exit that never answers is tolerated until it repeats, because the ladder
// it leads to ends by failing the session and retracting the CAN channel.
func TestUnansweredStreamExitsEscalateOnlyAfterTheLimit(t *testing.T) {
	port := &latePromptPort{profilePipelinePort: profilePipelinePort{protocolFrame: true, filteredFrame: true}}
	provider := latePromptProvider(t, port)
	provider.adapter.CommandWindow = 60 * time.Millisecond
	provider.Start()
	port.wedged.Store(true)
	// The adapter reset is the ladder's first rung. How far up it goes from
	// there depends on whether the adapter comes back, which is a different
	// question from the one this test asks.
	resets := countCommand(port.recordedCommands(), "ATZ")

	for burst := 1; burst < consecutiveExitTimeoutLimit; burst++ {
		if _, err := provider.ReadObservations(); err != nil {
			t.Fatal(err)
		}
		if got := countCommand(port.recordedCommands(), "ATZ"); got != resets {
			t.Fatalf("exit timeout %d escalated: ATZ count %d, want %d", burst, got, resets)
		}
		if status := provider.Status(); status != "" {
			t.Fatalf("exit timeout %d failed the session: %s", burst, status)
		}
	}
	if _, err := provider.ReadObservations(); err != nil {
		t.Fatal(err)
	}
	waitFor(t, "the run of unanswered exits to reach the adapter reset", func() bool {
		return countCommand(port.recordedCommands(), "ATZ") > resets
	})
}

// The failure that ends a session has to name the rung it stopped on: a USB
// reset that ran and did not revive the adapter and one that was never
// performed are different faults, and they ask different things of the owner.
func TestFailedRecoveryNamesWhetherTheUSBResetRan(t *testing.T) {
	for _, scenario := range []struct {
		name  string
		reset func(string) error
		want  string
	}{
		{"performed", func(string) error { return nil }, "after reset, reopen, and a USB reset"},
		{
			"skipped",
			func(string) error { return fmt.Errorf("%w: 1m0s ago", usbrecovery.ErrCoolingDown) },
			"no USB reset was performed",
		},
		{"failed", func(string) error { return errors.New("usbfs is not writable") }, "USB recovery failed"},
	} {
		t.Run(scenario.name, func(t *testing.T) {
			port := &escalationPort{profilePipelinePort: profilePipelinePort{protocolFrame: true, filteredFrame: true}}
			previousOpen := openOBDPort
			openOBDPort = func(string, *serial.Mode) (serial.Port, error) { return port, nil }
			t.Cleanup(func() { openOBDPort = previousOpen })
			provider := NewProfileProvider(NewOBDAdapter("scripted"), testDecoder(t))
			provider.trial = 5 * time.Millisecond
			provider.burstWindow = 5 * time.Millisecond
			provider.adapter.CommandWindow = 10 * time.Millisecond
			provider.wakePollInterval = time.Hour
			provider.auditInterval = time.Hour
			provider.SetUSBRecovery(scenario.reset)
			t.Cleanup(provider.Close)
			provider.Start()
			port.mute = true

			for burst := 0; burst < consecutiveExitTimeoutLimit; burst++ {
				if _, err := provider.ReadObservations(); err != nil {
					t.Fatal(err)
				}
			}
			waitFor(t, "the session to report why recovery ended", func() bool {
				return strings.Contains(provider.Status(), scenario.want)
			})
		})
	}
}

func TestProfileBurstWindowTracksSamplingCadence(t *testing.T) {
	if got := ProfileBurstWindow(time.Second); got != 300*time.Millisecond {
		t.Fatalf("one-second cadence window=%s, want 300ms", got)
	}
	if got := ProfileBurstWindow(15 * time.Second); got != time.Second {
		t.Fatalf("15-second cadence window=%s, want 1s", got)
	}
}

func TestOneSecondCadenceSampleCompletesWithinItsInterval(t *testing.T) {
	port := &profilePipelinePort{protocolFrame: true, filteredFrame: true}
	previousOpen := openOBDPort
	openOBDPort = func(string, *serial.Mode) (serial.Port, error) { return port, nil }
	t.Cleanup(func() { openOBDPort = previousOpen })
	provider := NewProfileProvider(NewOBDAdapter("scripted"), testDecoder(t))
	provider.trial = 10 * time.Millisecond
	provider.SetSamplingInterval(time.Second)
	provider.wakePollInterval = time.Hour
	provider.auditInterval = time.Hour
	defer provider.Close()
	provider.Start()
	state := provider.State()
	if !strings.Contains(state, "sample window 300ms") || !strings.Contains(state, "wake poll window 1s") {
		t.Fatalf("state=%q, want both diagnostic burst windows", state)
	}

	started := time.Now()
	observations, err := provider.ReadObservations()
	if err != nil {
		t.Fatal(err)
	}
	if elapsed := time.Since(started); elapsed >= time.Second {
		t.Fatalf("one-second cadence sample took %s", elapsed)
	}
	if got := observations["battery.soc"].Value; got != float64(67) {
		t.Fatalf("battery.soc=%v, want 67", got)
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

func TestStalledBurstReturnsCarriedSnapshotWithinBound(t *testing.T) {
	port := &escalationPort{profilePipelinePort: profilePipelinePort{protocolFrame: true, filteredFrame: true}}
	previousOpen := openOBDPort
	openOBDPort = func(string, *serial.Mode) (serial.Port, error) { return port, nil }
	t.Cleanup(func() { openOBDPort = previousOpen })
	provider := NewProfileProvider(NewOBDAdapter("scripted"), testDecoder(t))
	provider.trial = 5 * time.Millisecond
	provider.burstWindow = 20 * time.Millisecond
	provider.adapter.CommandWindow = 20 * time.Millisecond
	provider.wakePollInterval = time.Hour
	provider.auditInterval = time.Hour
	provider.SetUSBRecovery(func(string) error {
		time.Sleep(2 * (provider.burstWindow + burstCompletionAllowance))
		return errors.New("still stalled")
	})
	defer provider.Close()
	provider.Start()
	port.mute = true

	// The run of unanswered exits that puts the session into its stalled
	// recovery. Those bursts each finish inside the bound; the next one does not.
	for burst := 1; burst < consecutiveExitTimeoutLimit; burst++ {
		if _, err := provider.ReadObservations(); err != nil {
			t.Fatal(err)
		}
	}
	started := time.Now()
	observations, err := provider.ReadObservations()
	elapsed := time.Since(started)
	if err != nil {
		t.Fatal(err)
	}
	bound := provider.burstWindow + burstCompletionAllowance
	if elapsed < bound || elapsed > bound+150*time.Millisecond {
		t.Fatalf("stalled read took %s, want %s..%s", elapsed, bound, bound+150*time.Millisecond)
	}
	if got := observations["battery.soc"].Value; got != float64(67) {
		t.Fatalf("carried battery.soc=%v, want 67", got)
	}
	if state := provider.State(); !strings.Contains(state, "carried observations") {
		t.Fatalf("state=%q, want the carried reading disclosed", state)
	}
	t.Logf("stalled ReadObservations returned in %s (hard bound %s)", elapsed, bound)
}

func TestProfileCloseStopsRecoveryBeforeTheNextStep(t *testing.T) {
	port := &escalationPort{profilePipelinePort: profilePipelinePort{protocolFrame: true, filteredFrame: true}}
	previousOpen := openOBDPort
	openOBDPort = func(string, *serial.Mode) (serial.Port, error) { return port, nil }
	t.Cleanup(func() { openOBDPort = previousOpen })
	provider := NewProfileProvider(NewOBDAdapter("scripted"), testDecoder(t))
	provider.trial = 5 * time.Millisecond
	provider.burstWindow = 20 * time.Millisecond
	provider.adapter.CommandWindow = 20 * time.Millisecond
	provider.wakePollInterval = time.Hour
	provider.auditInterval = time.Hour
	provider.SetUSBRecovery(func(string) error {
		time.Sleep(2 * time.Second)
		return errors.New("still stalled")
	})
	provider.Start()
	port.mute = true
	// The adapter reset is the ladder's first step, so its ATZ is the evidence
	// that recovery is under way. Anchoring on the burst that precedes it proved
	// nothing about Close: a preparation command can fail before the stream even
	// starts, and then the burst being waited for never appears.
	baseline := countCommand(port.recordedCommands(), "ATZ")
	readDone := make(chan struct{})
	go func() {
		defer close(readDone)
		for attempt := 0; attempt < 10; attempt++ {
			if _, err := provider.ReadObservations(); err != nil {
				return
			}
			if countCommand(port.recordedCommands(), "ATZ") > baseline {
				return
			}
		}
	}()
	waitFor(t, "recovery to reach the adapter reset", func() bool {
		return countCommand(port.recordedCommands(), "ATZ") > baseline
	})

	started := time.Now()
	provider.Close()
	// The step already running still has to end: an ATZ deliberately waits a
	// second for the adapter to come back up. What must not happen is the rest of
	// the ladder — a re-prepare, a reopen and a stalled USB reset — running on
	// after the session was closed.
	if elapsed := time.Since(started); elapsed > 1500*time.Millisecond {
		t.Fatalf("Close waited %s behind recovery", elapsed)
	}
	select {
	case <-readDone:
	case <-time.After(2 * time.Second):
		t.Fatal("sample waiter outlived the closed recovery session")
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
	case command == "ATRV":
		port.pending = "12.4V\r>"
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

func countCommand(commands []string, target string) int {
	count := 0
	for _, command := range commands {
		if command == target {
			count++
		}
	}
	return count
}
