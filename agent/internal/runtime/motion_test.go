package runtime

import (
	"strings"
	"testing"
	"time"

	"github.com/Buco7854/carhibou/agent/internal/model"
)

type pollingPosition struct {
	fix *model.PositionFix
}

func (position *pollingPosition) Read() (*model.PositionFix, error)    { return position.fix, nil }
func (position *pollingPosition) PollFix() (*model.PositionFix, error) { return position.fix, nil }

func fixAt(latitude, longitude float64) *model.PositionFix {
	return &model.PositionFix{Latitude: latitude, Longitude: longitude}
}

// The drive that exposed this: the car was sampled before it started rolling,
// the next sample was scheduled ten minutes out, and the whole first leg
// happened inside that window. A vehicle with no readable speed has only its own
// displacement to announce itself with, and nothing was looking.
func TestParkedVehicleThatMovesRaisesAMotionEvent(t *testing.T) {
	position := &pollingPosition{fix: fixAt(48.8000, 2.3000)}
	agent := newAgent(t, position)
	agent.DrivingReportingInterval = 30
	agent.ParkedReportingInterval = 600
	now := time.Now()

	// The car is sitting there, sampled on the parked cadence.
	parked, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if parked.Agent["vehicle_in_use"] != false {
		t.Fatalf("vehicle_in_use=%v, want a parked car parked", parked.Agent["vehicle_in_use"])
	}

	// The first poll only anchors: one fix is not movement.
	if reason := agent.MotionEvent(now); reason != "" {
		t.Fatalf("a single fix raised motion: %q", reason)
	}
	// Still parked a few seconds later, a few metres out.
	position.fix = fixAt(48.80003, 2.3000)
	if reason := agent.MotionEvent(now.Add(2 * time.Second)); reason != "" {
		t.Fatalf("fix wander raised motion: %q", reason)
	}

	// Pulling away: several hundred metres inside the anchor window.
	position.fix = fixAt(48.8030, 2.3000)
	reason := agent.MotionEvent(now.Add(20 * time.Second))
	if !strings.Contains(reason, "moved") {
		t.Fatalf("reason=%q, want the departure reported", reason)
	}

	// The sample it arms is stamped, and the activity detector agrees the
	// vehicle is in use, which is what moves it onto the driving cadence.
	sample, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if sample.Agent["sample_trigger"] != reason {
		t.Fatalf("sample_trigger=%v, want %q", sample.Agent["sample_trigger"], reason)
	}
	if sample.Agent["vehicle_in_use"] != true {
		t.Fatalf("vehicle_in_use=%v, want the departure to flip the cadence", sample.Agent["vehicle_in_use"])
	}
	if sample.ReportingInterval == nil || *sample.ReportingInterval != 30 {
		t.Fatalf("reporting interval=%v, want the driving cadence", sample.ReportingInterval)
	}
}

// Once the vehicle is known to be in use the fast cadence is already running and
// there is nothing left for displacement to discover.
func TestMotionIsNotWatchedWhileAlreadyDriving(t *testing.T) {
	position := &pollingPosition{fix: fixAt(48.8000, 2.3000)}
	agent := newAgent(t, position)
	agent.InUse = true
	now := time.Now()
	agent.MotionEvent(now)
	position.fix = fixAt(48.8100, 2.3000)
	if reason := agent.MotionEvent(now.Add(10 * time.Second)); reason != "" {
		t.Fatalf("a driving vehicle raised a departure: %q", reason)
	}
}

// Slow drift across a long parked gap must not accumulate into a departure, so
// displacement is only ever measured over a bounded window.
func TestDriftAcrossALongGapDoesNotBecomeADeparture(t *testing.T) {
	position := &pollingPosition{fix: fixAt(48.8000, 2.3000)}
	agent := newAgent(t, position)
	now := time.Now()
	agent.MotionEvent(now)

	// Far enough to trigger, but the anchor is older than the window, so it is
	// replaced rather than compared against.
	position.fix = fixAt(48.8030, 2.3000)
	if reason := agent.MotionEvent(now.Add(10 * time.Minute)); reason != "" {
		t.Fatalf("a stale anchor produced a departure: %q", reason)
	}
}

// A source that costs a command exchange per read is not polled between samples.
func TestASourceWithoutACheapReadIsNotPolled(t *testing.T) {
	agent := newAgent(t, freshPosition{fix: fixAt(48.8, 2.3)})
	if reason := agent.MotionEvent(time.Now()); reason != "" {
		t.Fatalf("reason=%q, want no polling of an expensive source", reason)
	}
}
