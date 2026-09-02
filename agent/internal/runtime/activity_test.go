package runtime

import (
	"testing"
	"time"

	"github.com/Buco7854/carhibou/agent/internal/model"
)

func at(latitude, longitude float64, speed *float64) model.Sample {
	return model.Sample{Position: &model.PositionObservation{Value: model.PositionFix{Latitude: latitude, Longitude: longitude, Speed: speed}}}
}

func metrics(values map[string]any) model.Sample {
	observations := make([]model.Observation, 0, len(values))
	for key, value := range values {
		observations = append(observations, model.Observation{Key: key, Value: value})
	}
	return model.Sample{Observations: observations}
}

func TestReadinessOutranksEverythingWeaker(t *testing.T) {
	moving := 90.0
	detector := &ActivityDetector{}

	sample := at(48.8, 2.3, &moving)
	sample = withMetrics(sample, map[string]any{"vehicle.ready": false, "vehicle.speed": 90, "engine.rpm": 900})
	// A receiver still reporting speed, and an engine speed left over from the
	// last read, do not outrank the vehicle saying its ignition is off.
	if active, source := detector.Observe(sample, time.Now()); active || source != SourceIdle {
		t.Fatalf("a vehicle saying it is not ready must be parked, got active=%v source=%s", active, source)
	}

	sample = withMetrics(sample, map[string]any{"vehicle.ready": true})
	if active, source := detector.Observe(sample, time.Now()); !active || source != SourceReadiness {
		t.Fatalf("a vehicle saying it is ready must be active, got active=%v source=%s", active, source)
	}
}

// A car on a charger is a parked car. Counting the charge as use ran the driving
// cadence all evening for a vehicle sitting on a driveway; the endpoints of the
// charge are reported by its start and stop events, which owe nothing to cadence.
func TestChargingIsParked(t *testing.T) {
	detector := &ActivityDetector{}
	active, source := detector.Observe(metrics(map[string]any{"charging.active": true}), time.Now())
	if active || source != SourceIdle {
		t.Fatalf("a charging vehicle must be parked, got active=%v source=%s", active, source)
	}
}

// Charging stops being evidence on its own; it does not stop a vehicle that is
// plainly in use from being recognised.
func TestAReadyVehicleIsInUseWhileCharging(t *testing.T) {
	detector := &ActivityDetector{}
	sample := metrics(map[string]any{"vehicle.ready": true, "charging.active": true})
	if active, source := detector.Observe(sample, time.Now()); !active || source != SourceReadiness {
		t.Fatalf("readiness must still decide, got active=%v source=%s", active, source)
	}
}

// "Not charging" says nothing about whether a vehicle is moving, so it must not
// discard the readings of one that is. It used to: charging.active was treated as
// a readiness claim, and a stated false short-circuited every source below it. On
// a profile that decodes charging but not readiness - the C-Zero - that made a car
// doing ninety read as parked.
func TestNotChargingDoesNotOverruleMotion(t *testing.T) {
	now := time.Now()
	for _, test := range []struct {
		name    string
		metrics map[string]any
		want    ActivitySource
	}{
		{"speed", map[string]any{"charging.active": false, "vehicle.speed": 90.0}, SourceSpeed},
		{"engine", map[string]any{"charging.active": false, "engine.rpm": 900.0}, SourceEngine},
	} {
		detector := &ActivityDetector{}
		active, source := detector.Observe(metrics(test.metrics), now)
		if !active || source != test.want {
			t.Fatalf("%s: active=%v source=%s, want %s", test.name, active, source, test.want)
		}
	}

	// With nothing moving, a stated false is still a parked vehicle.
	detector := &ActivityDetector{}
	if active, _ := detector.Observe(metrics(map[string]any{"charging.active": false}), now); active {
		t.Fatal("a vehicle that is neither charging nor moving is parked")
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
	sample = withMetrics(sample, map[string]any{"vehicle.ready": false})
	if active, source := (&ActivityDetector{}).Observe(sample, now); active || source != SourceIdle {
		t.Fatalf("active=%v source=%s, want a stated false to hold", active, source)
	}
}

func withMetrics(sample model.Sample, values map[string]any) model.Sample {
	sample.Observations = metrics(values).Observations
	return sample
}

// The field case: a C-Zero whose CAN bus lingers awake for minutes after the
// ignition is switched off. It re-delivered an odometer and a lights state at a
// standstill and the agent ran the driving cadence for a full grace period at
// home. Metrics arriving is not evidence of motion; only motion is.
func TestALingeringBusAtAStandstillStaysParked(t *testing.T) {
	still := 0.0
	now := time.Now()
	detector := &ActivityDetector{Grace: time.Minute}

	parked := at(48.8000, 2.3000, &still)
	if active, _ := detector.Observe(parked, now); active {
		t.Fatal("a stationary vehicle with no evidence must start parked")
	}

	// The bus wakes and re-publishes what it knows. None of it is motion.
	lingering := withMetrics(at(48.8000, 2.3000, &still), map[string]any{
		"vehicle.odometer": 72066.0,
		"vehicle.lights":   "sidelights",
		"vehicle.speed":    0.0,
	})
	for round := 0; round < 4; round++ {
		if active, source := detector.Observe(lingering, now.Add(time.Duration(round)*time.Minute)); active {
			t.Fatalf("a lingering bus made a parked car active via %s", source)
		}
	}
}

// The mechanism that armed it: the anchor used to be frozen at the last sample
// where evidence fired, so the distance a car covered while coming to a stop was
// measured again, once, as new movement after it had already parked.
func TestParkingDoesNotReplayTheEndOfTheDriveAsMovement(t *testing.T) {
	moving := 50.0
	still := 0.0
	now := time.Now()
	detector := &ActivityDetector{Grace: time.Minute}

	// Driving: speed is the evidence, and the anchor tracks the vehicle.
	if active, source := detector.Observe(at(48.8000, 2.3000, &moving), now); !active || source != SourceSpeed {
		t.Fatalf("active=%v source=%s, want the drive recognised", active, source)
	}
	// It travels on for the last few hundred metres and stops.
	if active, _ := detector.Observe(at(48.8030, 2.3000, &still), now.Add(30*time.Second)); !active {
		t.Fatal("the grace period should still hold immediately after a drive")
	}
	// Well past the grace period, sitting still at the place it parked.
	resting := at(48.8030, 2.3000, &still)
	if active, source := detector.Observe(resting, now.Add(10*time.Minute)); active {
		t.Fatalf("a parked car was re-activated by its own arrival via %s", source)
	}
}

// A receiver that cannot locate itself to better than a hundred metres has not
// witnessed sixty metres of travel.
func TestMovementIsNotBelievedBeyondTheFixesOwnAccuracy(t *testing.T) {
	still := 0.0
	vague := 150.0
	now := time.Now()
	detector := &ActivityDetector{Grace: time.Minute}

	anchor := at(48.8000, 2.3000, &still)
	anchor.Position.Value.Accuracy = &vague
	detector.Observe(anchor, now)

	// A hundred metres away, from a fix admitting to a hundred and fifty.
	drifted := at(48.8009, 2.3000, &still)
	drifted.Position.Value.Accuracy = &vague
	if active, source := detector.Observe(drifted, now.Add(10*time.Minute)); active {
		t.Fatalf("uncertainty was read as travel via %s", source)
	}

	// The same displacement from a receiver that knows where it is, is motion.
	sharp := 5.0
	confident := at(48.8009, 2.3000, &still)
	confident.Position.Value.Accuracy = &sharp
	fresh := &ActivityDetector{Grace: time.Minute}
	base := at(48.8000, 2.3000, &still)
	base.Position.Value.Accuracy = &sharp
	fresh.Observe(base, now)
	if active, source := fresh.Observe(confident, now.Add(10*time.Minute)); !active || source != SourceMovement {
		t.Fatalf("active=%v source=%s, want a confident fix believed", active, source)
	}
}
