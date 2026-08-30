package providers

import (
	"strings"
	"testing"
	"time"

	"github.com/Buco7854/carhibou/agent/internal/model"
)

func wakeProvider(t *testing.T) *ProfileProvider {
	t.Helper()
	provider := NewProfileProvider(NewOBDAdapter("scripted"), testDecoder(t))
	provider.quietSettle = 30 * time.Millisecond
	return provider
}

func frameAt(canID int, at time.Time) model.CANFrame {
	return model.CANFrame{
		CANID:     canID,
		Data:      []byte{0x00, 0x90, 0, 0, 0, 0, 0, 0},
		Timestamp: float64(at.UnixNano()) / float64(time.Second),
	}
}

func profileFrame(at time.Time) model.CANFrame { return frameAt(0x374, at) }

// The reported case: the car is switched on without being driven. No metric this
// profile decodes changes, so nothing in the event-metric list flips, and the
// parked cadence is ten minutes away. Traffic itself has to be the evidence.
func TestFirstFrameAfterSilenceIsAWakeEvent(t *testing.T) {
	provider := wakeProvider(t)
	provider.monitorStartedAt = time.Now().UTC().Add(-2 * busWakeQuiet)

	provider.record(profileFrame(time.Now().UTC()))
	reason := provider.TakeEvent()
	if !strings.Contains(reason, "woke") {
		t.Fatalf("reason=%q, want the wake reported", reason)
	}
	// A bus that keeps talking is not waking over and over.
	provider.record(profileFrame(time.Now().UTC()))
	if second := provider.TakeEvent(); second != "" {
		t.Fatalf("continuing traffic raised another wake: %q", second)
	}
}

// Starting the service against a car that is already running is not a wake.
func TestStartingOnALiveBusIsNotAWakeEvent(t *testing.T) {
	provider := wakeProvider(t)
	provider.monitorStartedAt = time.Now().UTC()

	provider.record(profileFrame(time.Now().UTC()))
	if reason := provider.TakeEvent(); reason != "" {
		t.Fatalf("starting on a live bus raised a wake: %q", reason)
	}
}

// A frame arriving on an identifier this profile never asked for still proves
// the vehicle is awake. The wake trigger is deliberately profile-independent.
func TestWakeIsNoticedOnTrafficThisProfileIgnores(t *testing.T) {
	provider := wakeProvider(t)
	provider.monitorStartedAt = time.Now().UTC().Add(-2 * busWakeQuiet)

	provider.record(frameAt(0x101, time.Now().UTC()))
	if reason := provider.TakeEvent(); !strings.Contains(reason, "woke") {
		t.Fatalf("reason=%q, want unrelated traffic to count as a wake", reason)
	}
}

// Ignition off: the bus stops. The sample this fires carries the closing values
// of the drive, which is why it must not wait for the parked cadence.
func TestBusGoingQuietFiresExactlyOneEventCarryingTheFinalValues(t *testing.T) {
	provider := wakeProvider(t)
	provider.monitorStartedAt = time.Now().UTC()
	provider.record(profileFrame(time.Now().UTC()))
	provider.TakeEvent()

	// Too soon: a gap between broadcasts is not the ignition going off.
	provider.noteQuietOnset(time.Now().UTC())
	if reason := provider.TakeEvent(); reason != "" {
		t.Fatalf("a momentary gap was called sleep: %q", reason)
	}

	settled := time.Now().UTC().Add(provider.quietSettle + time.Millisecond)
	provider.noteQuietOnset(settled)
	reason := provider.TakeEvent()
	if !strings.Contains(reason, "quiet") {
		t.Fatalf("reason=%q, want the bus going quiet reported", reason)
	}

	// Exactly one: the state is already quiet, so later checks add nothing.
	provider.noteQuietOnset(settled.Add(time.Second))
	if second := provider.TakeEvent(); second != "" {
		t.Fatalf("a second quiet event fired: %q", second)
	}

	// And the values the drive ended on are still there to be sampled.
	observations, err := provider.ReadObservations()
	if err != nil {
		t.Fatal(err)
	}
	if observations["battery.soc"].Value != float64(67) {
		t.Fatalf("observations=%#v, want the drive's closing values retained", observations)
	}
}

// A bus on the edge of sleep flaps. That must cost one event, not a storm.
func TestFlappingBusDoesNotStormEvents(t *testing.T) {
	provider := wakeProvider(t)
	provider.monitorStartedAt = time.Now().UTC()
	at := time.Now().UTC()
	provider.record(profileFrame(at))
	provider.TakeEvent()

	raised := 0
	for cycle := 0; cycle < 8; cycle++ {
		at = at.Add(provider.quietSettle + time.Millisecond)
		provider.noteQuietOnset(at)
		if provider.TakeEvent() != "" {
			raised++
		}
		at = at.Add(time.Millisecond)
		provider.record(profileFrame(at))
		if provider.TakeEvent() != "" {
			raised++
		}
	}
	// The debounce window is far longer than the whole flapping sequence, so one
	// report is the most that can escape it.
	if raised > 1 {
		t.Fatalf("flapping raised %d events, want at most one", raised)
	}
}

// residuePort answers ATRV only after the leftovers of a frame stream, which is
// what a real adapter does when a command follows a monitor too closely.
type residuePort struct {
	scriptedPort
	replies []string
	served  int
}

func (port *residuePort) Write(payload []byte) (int, error) {
	if port.served < len(port.replies) {
		port.pending = port.replies[port.served]
		port.served++
	} else {
		port.pending = ">"
	}
	return len(payload), nil
}

// The selftest came back with raw CAN bytes in its adapter and firmware fields,
// which is a command reply built out of whatever the previous stream had left
// behind. A frame line must never be mistaken for an answer.
func TestSupplyReadingIgnoresFrameResidueAndRetriesOnce(t *testing.T) {
	port := &residuePort{replies: []string{
		"374 8 00 90 00 00 00 00 00 00\r12.4V\r>",
	}}
	adapter := NewOBDAdapter("scripted")
	adapter.port = port
	adapter.CommandWindow = 200 * time.Millisecond

	reading, err := adapter.Voltage()
	if err != nil {
		t.Fatal(err)
	}
	if reading != "12.4V" {
		t.Fatalf("voltage=%q, want the voltage rather than the frame", reading)
	}
	if value, ok := ParseSupplyVoltage(reading); !ok || value != 12.4 {
		t.Fatalf("parsed=%v ok=%v", value, ok)
	}
}

// A reply that is nothing but residue is retried rather than believed.
func TestSupplyReadingRetriesWhenTheWholeReplyIsResidue(t *testing.T) {
	port := &residuePort{replies: []string{
		"374 8 00 90 00 00 00 00 00 00\r>",
		"12.6V\r>",
	}}
	adapter := NewOBDAdapter("scripted")
	adapter.port = port
	adapter.CommandWindow = 200 * time.Millisecond

	reading, err := adapter.Voltage()
	if err != nil {
		t.Fatal(err)
	}
	if reading != "12.6V" {
		t.Fatalf("voltage=%q, want the retry to find the real reading", reading)
	}
	if port.served != 2 {
		t.Fatalf("served=%d replies, want exactly one retry", port.served)
	}
}

// A frame line must not parse as a voltage in the first place.
func TestFrameLinesAreNotVoltages(t *testing.T) {
	for _, line := range []string{
		"374 8 00 90 00 00 00 00 00 00",
		"BUFFER FULL",
		"STOPPED",
		"",
		"99V",
	} {
		if _, ok := ParseSupplyVoltage(line); ok {
			t.Fatalf("%q was accepted as a supply voltage", line)
		}
	}
	if value, ok := ParseSupplyVoltage(" 12.4V "); !ok || value != 12.4 {
		t.Fatalf("a real reading was rejected: value=%v ok=%v", value, ok)
	}
}

// Leaving a stream must hand back a clean prompt: anything still buffered
// belongs to the stream, not to the next question.
func TestLeavingAStreamDiscardsWhatTheStreamLeftBehind(t *testing.T) {
	port := &scriptedPort{replies: map[string]string{
		"": "374 8 00 90 00 00 00 00 00 00\r>374 8 00 91 00 00 00 00 00 00\r",
	}}
	adapter := NewOBDAdapter("scripted")
	adapter.port = port
	adapter.CommandWindow = 200 * time.Millisecond

	if err := adapter.leaveStream(func(string) {}); err != nil {
		t.Fatal(err)
	}
	if adapter.pending != "" {
		t.Fatalf("pending=%q, want the residue discarded", adapter.pending)
	}
}
