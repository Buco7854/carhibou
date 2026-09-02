package providers

import (
	"strings"
	"testing"
	"time"
)

func silentProvider(t *testing.T, opened time.Time, lastFix time.Time) *NMEAProvider {
	t.Helper()
	provider := NewNMEAProvider("/dev/carhibou-test")
	provider.opened = opened
	provider.lastFix = lastFix
	return provider
}

// The field case: the module goes mute. Until the receiver could say so, a port
// streaming nothing was indistinguishable from a vehicle underground, and the
// agent reported neither.
func TestSilentReceiverBecomesAStateThenAFailure(t *testing.T) {
	now := time.Now()

	fresh := silentProvider(t, now.Add(-time.Minute), now.Add(-time.Second))
	if state := fresh.State(); state != "" {
		t.Fatalf("state=%q, want silence about a receiver that just reported", state)
	}
	if status := fresh.Status(); status != "" {
		t.Fatalf("status=%q, want no fault", status)
	}

	quiet := silentProvider(t, now.Add(-5*time.Minute), now.Add(-(QuietWindow + 15*time.Second)))
	if state := quiet.State(); !strings.Contains(state, "quiet") {
		t.Fatalf("state=%q, want the quiet receiver named", state)
	}
	if status := quiet.Status(); status != "" {
		t.Fatalf("status=%q, want a searching receiver to stay a state", status)
	}

	gone := silentProvider(t, now.Add(-time.Hour), now.Add(-(DeadWindow + time.Minute)))
	if status := gone.Status(); !strings.Contains(status, "no NMEA sentences") {
		t.Fatalf("status=%q, want the dead receiver reported as a fault", status)
	}
	if state := gone.State(); state != "" {
		t.Fatalf("state=%q, want a fault to stop being merely a state", state)
	}
}

// A receiver that has never produced a fix is judged from when the port opened.
// Measuring from a zero timestamp read as no elapsed time, so a receiver that
// never worked looked like one that had just answered.
func TestReceiverThatNeverReportedIsJudgedFromWhenThePortOpened(t *testing.T) {
	provider := silentProvider(t, time.Now().Add(-(DeadWindow + time.Minute)), time.Time{})
	if status := provider.Status(); !strings.Contains(status, "no NMEA sentences") {
		t.Fatalf("status=%q, want a receiver that never spoke reported", status)
	}

	justOpened := silentProvider(t, time.Now(), time.Time{})
	if status := justOpened.Status(); status != "" {
		t.Fatalf("status=%q, want a receiver a moment old given time to speak", status)
	}
}

// A port that will not open is the other half of the same question, and names
// the device so the journal says which one.
func TestUnopenablePortIsReportedWithItsDevice(t *testing.T) {
	provider := NewNMEAProvider("/dev/carhibou-absent")
	if _, err := provider.Read(); err == nil {
		t.Fatal("expected opening a missing device to fail")
	}
	status := provider.Status()
	if !strings.Contains(status, "/dev/carhibou-absent") || !strings.Contains(status, "failed to open") {
		t.Fatalf("status=%q, want the device and the failure named", status)
	}
}
