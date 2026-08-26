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
	sample.Metrics = map[string]any{"vehicle.ready": false, "vehicle.speed": 90, "engine.rpm": 900}
	// A receiver still reporting speed, and an engine speed left over from the
	// last read, do not outrank the vehicle saying its ignition is off.
	if active, source := detector.Observe(sample, time.Now()); active || source != SourceIdle {
		t.Fatalf("a vehicle saying it is not ready must be parked, got active=%v source=%s", active, source)
	}

	sample.Metrics = map[string]any{"vehicle.ready": true}
	if active, source := detector.Observe(sample, time.Now()); !active || source != SourceReadiness {
		t.Fatalf("a vehicle saying it is ready must be active, got active=%v source=%s", active, source)
	}
}

func TestChargingCountsAsInUse(t *testing.T) {
	detector := &ActivityDetector{}
	active, source := detector.Observe(metrics(map[string]any{"charging.active": true}), time.Now())
	if !active || source != SourceReadiness {
		t.Fatalf("a charging vehicle must keep the fast cadence, got active=%v source=%s", active, source)
	}
}

// Each source has to work on its own, because an agent may have any subset of
// them: no profile, no adapter, or a receiver that reports no speed field.
func TestEachSourceStandsAlone(t *testing.T) {
	now := time.Now()
	moving, still := 40.0, 0.0

	if active, source := (&ActivityDetector{}).Observe(metrics(map[string]any{"engine.rpm": 850}), now); !active || source != SourceEngine {
		t.Fatalf("a turning engine alone must be active, got active=%v source=%s", active, source)
	}
	// Zero covers a stop-start system at a light and every electric vehicle, so
	// it must not park anything on its own.
	if active, _ := (&ActivityDetector{}).Observe(metrics(map[string]any{"engine.rpm": 0, "vehicle.speed": 50}), now); !active {
		t.Fatal("a stopped engine must not overrule road speed")
	}
	if active, source := (&ActivityDetector{}).Observe(metrics(map[string]any{"vehicle.speed": 42}), now); !active || source != SourceSpeed {
		t.Fatalf("decoded speed alone must be active, got active=%v source=%s", active, source)
	}
	if active, source := (&ActivityDetector{}).Observe(at(48.8, 2.3, &moving), now); !active || source != SourceSpeed {
		t.Fatalf("GPS speed alone must be active, got active=%v source=%s", active, source)
	}

	// Displacement is the last resort: no readiness, no bus, no speed field.
	// No readiness signal, no engine speed, no road speed: only where it was.
	detector := &ActivityDetector{}
	detector.Observe(at(48.8000, 2.3000, &still), now)
	far := at(48.8100, 2.3000, &still)
	if active, source := detector.Observe(far, now.Add(time.Hour)); !active || source != SourceMovement {
		t.Fatalf("a kilometre of displacement must be active, got active=%v source=%s", active, source)
	}
}

func TestStationaryNoiseDoesNotCountAsMovement(t *testing.T) {
	still := 0.4
	now := time.Now()
	detector := &ActivityDetector{Grace: time.Minute}
	detector.Observe(at(48.800000, 2.300000, &still), now)

	// Roughly ten metres away, and a tenth of a knot: a parked car's fix wander.
	drifted := at(48.800090, 2.300000, &still)
	if active, source := detector.Observe(drifted, now.Add(2*time.Minute)); active {
		t.Fatalf("fix noise must not read as motion, got active=%v source=%s", active, source)
	}
}

func TestGraceHoldsThroughAStopThenReleases(t *testing.T) {
	now := time.Now()
	detector := &ActivityDetector{Grace: 3 * time.Minute}
	detector.Observe(metrics(map[string]any{"engine.rpm": 800}), now)

	if active, source := detector.Observe(model.Sample{}, now.Add(time.Minute)); !active || source != SourceGrace {
		t.Fatalf("a minute at a light must stay active, got active=%v source=%s", active, source)
	}
	if active, source := detector.Observe(model.Sample{}, now.Add(4*time.Minute)); active || source != SourceIdle {
		t.Fatalf("four minutes of silence must park, got active=%v source=%s", active, source)
	}
}

// An agent that has just booted has no evidence of anything, and must not spend
// its first grace period uploading at the driving cadence on every restart.
func TestAFreshDetectorStartsParked(t *testing.T) {
	if active, source := (&ActivityDetector{}).Observe(model.Sample{}, time.Now()); active || source != SourceIdle {
		t.Fatalf("a fresh detector must start parked, got active=%v source=%s", active, source)
	}
}

// An agent that starts up beside a parked car has no evidence of anything, so
// its only remaining source is that the car later moved. That needs an anchor,
// which is set from the first fix rather than from the first active sample.
func TestDisplacementWorksForAAgentThatStartedParked(t *testing.T) {
	still := 0.0
	now := time.Now()
	detector := &ActivityDetector{Grace: time.Minute}

	if active, _ := detector.Observe(at(48.8000, 2.3000, &still), now); active {
		t.Fatal("a stationary vehicle with no other evidence must start parked")
	}
	// Towed, or driven by something this agent cannot read.
	if active, source := detector.Observe(at(48.8100, 2.3000, &still), now.Add(time.Hour)); !active || source != SourceMovement {
		t.Fatalf("movement must be noticed, got active=%v source=%s", active, source)
	}
}

// A sample without a fix must not discard the anchor, or one gap in reception
// would restart the comparison from wherever the vehicle happened to be next.
func TestAGapInReceptionKeepsTheAnchor(t *testing.T) {
	still := 0.0
	now := time.Now()
	detector := &ActivityDetector{Grace: time.Minute}
	detector.Observe(at(48.8000, 2.3000, &still), now)
	detector.Observe(model.Sample{}, now.Add(time.Minute))

	if active, source := detector.Observe(at(48.8100, 2.3000, &still), now.Add(2*time.Minute)); !active || source != SourceMovement {
		t.Fatalf("the anchor must survive a missing fix, got active=%v source=%s", active, source)
	}
}

// The agent recognises three canonical booleans and no vehicle-specific words, so
// a vehicle whose states it has never heard of falls through to motion rather than
// being judged by a claim nobody made.
func TestAnUnmappedStateFallsThroughToMotion(t *testing.T) {
	moving := 40.0
	now := time.Now()

	// The profile published nothing for this state, so the readiness rule does not
	// apply and speed decides.
	sample := at(48.8, 2.3, &moving)
	if active, source := (&ActivityDetector{}).Observe(sample, now); !active || source != SourceSpeed {
		t.Fatalf("active=%v source=%s, want the vehicle judged by motion", active, source)
	}

	// A stated false still outranks motion, because that is a claim.
	sample.Metrics = map[string]any{"vehicle.ready": false}
	if active, source := (&ActivityDetector{}).Observe(sample, now); active || source != SourceIdle {
		t.Fatalf("active=%v source=%s, want a stated false to hold", active, source)
	}
}
