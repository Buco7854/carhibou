package providers

import (
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Buco7854/carhibou/agent/internal/model"
	"go.bug.st/serial"
)

const auditFrame = "374 8 00 90 00 00 00 00 00 00\r"

// wakeablePort is an adapter in front of a car that can be asleep or awake, on
// firmware whose hardware filters may or may not do anything. The combination is
// the whole point: a monitor that starts against a sleeping bus learns nothing
// about its own filters, and only a later wake reveals whether they work.
type wakeablePort struct {
	scriptedPort
	mutex       sync.Mutex
	buffered    string
	streaming   string
	awake       bool
	filtersWork bool
	// installed models the firmware this was found on: a filtered monitor with
	// no filters installed passes nothing at all, rather than everything. That
	// is what made protocol trials run before the filters structurally blind.
	installed bool
	commands  []string
	bursts    int
}

func (port *wakeablePort) setBus(awake, filtersWork bool) {
	port.mutex.Lock()
	defer port.mutex.Unlock()
	port.awake, port.filtersWork = awake, filtersWork
}

func (port *wakeablePort) burstCount() int {
	port.mutex.Lock()
	defer port.mutex.Unlock()
	return port.bursts
}

func (port *wakeablePort) recorded() []string {
	port.mutex.Lock()
	defer port.mutex.Unlock()
	return append([]string(nil), port.commands...)
}

func (port *wakeablePort) Write(payload []byte) (int, error) {
	command := strings.TrimSuffix(string(payload), "\r")
	port.mutex.Lock()
	defer port.mutex.Unlock()
	port.commands = append(port.commands, command)
	switch {
	case command == "":
		// A bare carriage return leaves the stream and returns to the prompt.
		port.streaming = ""
		port.buffered = ">"
	case command == "STM" || command == "STMA":
		port.streaming = command
		port.buffered = ""
		if command == "STMA" {
			port.bursts++
		}
	case strings.HasPrefix(command, "STFAP"):
		port.installed = true
		port.buffered = "OK\r>"
	case strings.HasPrefix(command, "ATSP") || command == "ATZ":
		// Changing protocol or resetting drops whatever filters were in place.
		port.installed = false
		port.buffered = "OK\r>"
	case command == "ATRV":
		port.buffered = "12.4V\r>"
	case strings.HasPrefix(command, "STBR"):
		port.buffered = "?\r>"
	default:
		port.buffered = "OK\r>"
	}
	return len(payload), nil
}

func (port *wakeablePort) Read(buffer []byte) (int, error) {
	port.mutex.Lock()
	if port.buffered == "" && port.streaming != "" && port.awake {
		// Broken filters are the case where STM is silent on a bus that is
		// plainly talking, which is exactly what STMA is asked to disprove.
		if port.streaming == "STMA" || (port.installed && port.filtersWork) {
			port.buffered = auditFrame
		}
	}
	if port.buffered == "" {
		port.mutex.Unlock()
		time.Sleep(2 * time.Millisecond)
		return 0, nil
	}
	count := copy(buffer, port.buffered)
	port.buffered = port.buffered[count:]
	port.mutex.Unlock()
	return count, nil
}

func auditProvider(t *testing.T, port *wakeablePort) *ProfileProvider {
	t.Helper()
	previousOpen := openOBDPort
	openOBDPort = func(string, *serial.Mode) (serial.Port, error) { return port, nil }
	t.Cleanup(func() { openOBDPort = previousOpen })

	provider := NewProfileProvider(NewOBDAdapter("scripted"), testDecoder(t))
	provider.trial = 15 * time.Millisecond
	provider.auditInterval = 40 * time.Millisecond
	provider.auditBurst = 20 * time.Millisecond
	provider.adapter.CommandWindow = 300 * time.Millisecond
	t.Cleanup(provider.Close)
	return provider
}

func waitFor(t *testing.T, why string, condition func() bool) {
	t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		if condition() {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatalf("timed out waiting for %s", why)
}

// The reported defect: the service starts while the car sleeps, so neither
// monitor proves anything, and the filtered stream it settles on is deaf for the
// rest of the session on firmware whose filters drop everything. Every later
// wake then produced nothing but the supply reading.
func TestSleepingStartLaterProvesFiltersBrokenAndFallsBack(t *testing.T) {
	port := &wakeablePort{}
	provider := auditProvider(t, port)
	provider.Start()

	if provider.unfiltered {
		t.Fatal("a start against a sleeping bus proves nothing and must not fall back yet")
	}
	if state := provider.State(); !strings.Contains(state, "monitor: filtered") {
		t.Fatalf("state=%q, want the filtered mode named", state)
	}

	// The car wakes, but this adapter's filters silently drop everything.
	port.setBus(true, false)
	waitFor(t, "the audit to prove the filters ineffective", func() bool {
		provider.mutex.Lock()
		defer provider.mutex.Unlock()
		return provider.unfiltered
	})

	state := provider.State()
	if !strings.Contains(state, "unfiltered fallback") {
		t.Fatalf("state=%q, want the fallback published", state)
	}
	if !strings.Contains(state, "delivered nothing while the bus was live") {
		t.Fatalf("state=%q, want the switch attributed to the running audit", state)
	}
	// The fallback is a repair, not an equal option: unfiltered monitoring on a
	// live bus overflows the adapter, and the status has to say so.
	if !strings.Contains(state, "last resort") || !strings.Contains(state, "dropped frames") {
		t.Fatalf("state=%q, want the awake-bus hazard published", state)
	}

	// And the point of all of it: values decode again.
	waitFor(t, "decoding to resume", func() bool {
		observations, err := provider.ReadObservations()
		if err != nil {
			t.Fatal(err)
		}
		return observations["battery.soc"].Value == float64(67)
	})
	if provider.Status() != "" {
		t.Fatalf("a working fallback reported a failure: %q", provider.Status())
	}
}

// The same sleeping start on firmware whose filters work must leave the filtered
// monitor alone: the fallback is a repair, not a preference.
func TestSleepingStartWithWorkingFiltersNeverFallsBack(t *testing.T) {
	port := &wakeablePort{}
	provider := auditProvider(t, port)
	provider.Start()

	port.setBus(true, true)
	waitFor(t, "the filtered stream to decode", func() bool {
		observations, err := provider.ReadObservations()
		if err != nil {
			t.Fatal(err)
		}
		return observations["battery.soc"].Value == float64(67)
	})

	// Give the audit several opportunities it should decline to take.
	time.Sleep(6 * provider.auditInterval)
	provider.mutex.Lock()
	fellBack := provider.unfiltered
	provider.mutex.Unlock()
	if fellBack {
		t.Fatal("a filtered monitor that is delivering frames must not be replaced")
	}
	if state := provider.State(); !strings.Contains(state, "monitor: filtered") {
		t.Fatalf("state=%q, want the filtered mode still named", state)
	}
}

// A bus that is simply asleep must keep re-arming quietly: bursts continue, no
// fallback is declared on the strength of silence, and the status does not churn.
func TestQuietBusKeepsReArmingWithoutStatusChurn(t *testing.T) {
	port := &wakeablePort{}
	provider := auditProvider(t, port)
	provider.Start()

	waitFor(t, "the audit to have burst more than once", func() bool { return port.burstCount() >= 2 })
	time.Sleep(3 * provider.auditInterval)

	provider.mutex.Lock()
	fellBack := provider.unfiltered
	provider.mutex.Unlock()
	if fellBack {
		t.Fatal("silence is not evidence that filters are broken")
	}
	if status := provider.Status(); status != "" {
		t.Fatalf("a sleeping bus reported a failure: %q", status)
	}
	state := provider.State()
	if !strings.Contains(state, "monitor: filtered") || !strings.Contains(state, "bus quiet") {
		t.Fatalf("state=%q, want the filtered mode and the quiet bus", state)
	}
	// Every burst hands the filtered stream back rather than abandoning it. The
	// last command is not the assertion: sampling can land mid-burst, and what
	// matters is that a burst is always followed by a resume.
	commands := port.recorded()
	lastBurst, resumedAfter := -1, false
	for index, command := range commands {
		if command == "STMA" {
			lastBurst, resumedAfter = index, false
		}
		if command == "STM" && lastBurst >= 0 && index > lastBurst {
			resumedAfter = true
		}
	}
	if lastBurst < 0 {
		t.Fatal("no unfiltered burst was ever attempted")
	}
	if !resumedAfter && commands[len(commands)-1] != "STMA" {
		t.Fatalf("commands=%v, want the filtered stream resumed after each burst", commands)
	}
}

// The defect the field data exposed: protocol trials listened before the filters
// were installed, and on this firmware an unfiltered-by-omission STM passes
// nothing. Every trial therefore reported silence on a wide-awake bus, and the
// only reason the right protocol was ever chosen was the fallback guess.
func TestProtocolTrialsListenWithFiltersInstalled(t *testing.T) {
	port := &wakeablePort{awake: true, filtersWork: true}
	previousOpen := openOBDPort
	openOBDPort = func(string, *serial.Mode) (serial.Port, error) { return port, nil }
	t.Cleanup(func() { openOBDPort = previousOpen })

	adapter := NewOBDAdapter("scripted")
	if err := adapter.Connect(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(adapter.Close)
	adapter.CommandWindow = 300 * time.Millisecond

	preparation, err := PrepareProfileMonitor(
		adapter, []int{0x374}, 30*time.Millisecond, 0, false, func(model.CANFrame) {},
		nil, time.Time{},
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(preparation.ProtocolTrials) == 0 {
		t.Fatal("no protocol was tried")
	}
	first := preparation.ProtocolTrials[0]
	if first.Trace.Report.ParsedFrames == 0 {
		t.Fatalf("the first trial heard nothing on a live bus: %+v", first)
	}
	if preparation.ProtocolCode != "6" {
		t.Fatalf("protocol=%q, want the one that actually carried frames", preparation.ProtocolCode)
	}
	if !preparation.HardwareFilterGood {
		t.Fatal("filters that delivered frames were not credited as working")
	}
	if preparation.UseUnfiltered {
		t.Fatal("a filtered monitor that works must never be replaced by STMA")
	}
	if len(preparation.FilterCommands) == 0 {
		t.Fatal("the filter installation was not recorded")
	}

	// Select, filter, listen: the filters must be installed between choosing the
	// protocol and listening on it, because ATSP drops them.
	recorded := port.recorded()
	protocol := commandIndex(recorded, "ATSP6", 0)
	filters := commandIndex(recorded, "STFAP 374,FFF", 0)
	listen := commandIndex(recorded, "STM", 0)
	if protocol < 0 || filters < 0 || listen < 0 || !(protocol < filters && filters < listen) {
		t.Fatalf("commands=%v, want ATSP6 then STFAP then STM", recorded)
	}
}

// Ignition off. The user's question was whether turning the car off is visible:
// a parked-but-on car never flips the in-use metric, so without this the answer
// was "at the next parked cadence", up to ten minutes later.
//
// This drives the real session rather than the detector directly, so it covers
// the part the unit test cannot: that the watcher goroutine is started, ticks,
// and reaches TakeEvent through a running monitor.
func TestLiveSessionRaisesOneEventWhenTheBusStops(t *testing.T) {
	port := &wakeablePort{awake: true, filtersWork: true}
	provider := auditProvider(t, port)
	provider.quietSettle = 60 * time.Millisecond
	provider.quietPoll = 10 * time.Millisecond
	provider.Start()

	waitFor(t, "the drive to decode", func() bool {
		observations, err := provider.ReadObservations()
		if err != nil {
			t.Fatal(err)
		}
		return observations["battery.soc"].Value == float64(67)
	})
	// Starting against a bus that is already talking is not a wake, so nothing
	// should be armed yet.
	if reason := provider.TakeEvent(); reason != "" {
		t.Fatalf("a live start armed an event: %q", reason)
	}

	port.setBus(false, true)
	var quietReason string
	waitFor(t, "the bus going quiet to be noticed", func() bool {
		quietReason = provider.TakeEvent()
		return quietReason != ""
	})
	if !strings.Contains(quietReason, "quiet") {
		t.Fatalf("reason=%q, want the bus going quiet reported", quietReason)
	}

	// Exactly one: the bus stays off and the transition has already been made.
	time.Sleep(6 * provider.quietSettle)
	if second := provider.TakeEvent(); second != "" {
		t.Fatalf("a still bus raised a second event: %q", second)
	}

	// The sample this arms carries where the drive ended, and the state says so.
	observations, err := provider.ReadObservations()
	if err != nil {
		t.Fatal(err)
	}
	if observations["battery.soc"].Value != float64(67) {
		t.Fatalf("observations=%#v, want the closing values retained", observations)
	}
	if state := provider.State(); !strings.Contains(state, "bus quiet") {
		t.Fatalf("state=%q, want the quiet bus published with the event", state)
	}
}
