package runtime

import (
	"testing"
	"time"

	"github.com/Buco7854/vehinode/agent/internal/model"
)

func at(latitude, longitude float64, speed *float64) model.Sample {
	return model.Sample{Position: &model.PositionFix{Latitude: latitude, Longitude: longitude, Speed: speed}}
}

func metrics(values map[string]any) model.Sample { return model.Sample{Metrics: values} }

func TestReadinessOutranksEverythingWeaker(t *testing.T) {
	moving := 90.0
	detector := &ActivityDetector{}

	sample := at(48.8, 2.3, &moving)
	sample.Metrics = map[string]any{"vehicle.ignition": false, "vehicle.speed": 90}
	// A receiver that still reports speed while the ignition is off is drifting,
	// not driving, so the vehicle it is bolted to is parked.
	if active, source := detector.Observe(sample, true, time.Now()); active || source != SourceIdle {
		t.Fatalf("ignition off must park the vehicle, got active=%v source=%s", active, source)
	}

	sample.Metrics = map[string]any{"vehicle.ignition": true}
	if active, source := detector.Observe(sample, false, time.Now()); !active || source != SourceReadiness {
		t.Fatalf("ignition on must be active, got active=%v source=%s", active, source)
	}
}

func TestChargingCountsAsInUse(t *testing.T) {
	detector := &ActivityDetector{}
	active, source := detector.Observe(metrics(map[string]any{"charging.active": true}), false, time.Now())
	if !active || source != SourceReadiness {
		t.Fatalf("a charging vehicle must keep the fast cadence, got active=%v source=%s", active, source)
	}
}

// Each source has to work on its own, because a tracker may have any subset of
// them: no profile, no adapter, or a receiver that reports no speed field.
func TestEachSourceStandsAlone(t *testing.T) {
	now := time.Now()
	moving, still := 40.0, 0.0

	if active, source := (&ActivityDetector{}).Observe(model.Sample{}, true, now); !active || source != SourceBus {
		t.Fatalf("live bus alone must be active, got active=%v source=%s", active, source)
	}
	if active, source := (&ActivityDetector{}).Observe(metrics(map[string]any{"vehicle.speed": 42}), false, now); !active || source != SourceSpeed {
		t.Fatalf("decoded speed alone must be active, got active=%v source=%s", active, source)
	}
	if active, source := (&ActivityDetector{}).Observe(at(48.8, 2.3, &moving), false, now); !active || source != SourceSpeed {
		t.Fatalf("GPS speed alone must be active, got active=%v source=%s", active, source)
	}

	// Displacement is the last resort: no readiness, no bus, no speed field.
	detector := &ActivityDetector{}
	detector.Observe(at(48.8000, 2.3000, &still), true, now)
	far := at(48.8100, 2.3000, &still)
	if active, source := detector.Observe(far, false, now.Add(time.Hour)); !active || source != SourceMovement {
		t.Fatalf("a kilometre of displacement must be active, got active=%v source=%s", active, source)
	}
}

func TestStationaryNoiseDoesNotCountAsMovement(t *testing.T) {
	still := 0.4
	now := time.Now()
	detector := &ActivityDetector{Grace: time.Minute}
	detector.Observe(at(48.800000, 2.300000, &still), true, now)

	// Roughly ten metres away, and a tenth of a knot: a parked car's fix wander.
	drifted := at(48.800090, 2.300000, &still)
	if active, source := detector.Observe(drifted, false, now.Add(2*time.Minute)); active {
		t.Fatalf("fix noise must not read as motion, got active=%v source=%s", active, source)
	}
}

func TestGraceHoldsThroughAStopThenReleases(t *testing.T) {
	now := time.Now()
	detector := &ActivityDetector{Grace: 3 * time.Minute}
	detector.Observe(model.Sample{}, true, now)

	if active, source := detector.Observe(model.Sample{}, false, now.Add(time.Minute)); !active || source != SourceGrace {
		t.Fatalf("a minute at a light must stay active, got active=%v source=%s", active, source)
	}
	if active, source := detector.Observe(model.Sample{}, false, now.Add(4*time.Minute)); active || source != SourceIdle {
		t.Fatalf("four minutes of silence must park, got active=%v source=%s", active, source)
	}
}

// A tracker that has just booted has no evidence of anything, and must not spend
// its first grace period uploading at the driving cadence on every restart.
func TestAFreshDetectorStartsParked(t *testing.T) {
	if active, source := (&ActivityDetector{}).Observe(model.Sample{}, false, time.Now()); active || source != SourceIdle {
		t.Fatalf("a fresh detector must start parked, got active=%v source=%s", active, source)
	}
}
