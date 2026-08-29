package runtime

import (
	"testing"
	"time"

	"github.com/Buco7854/carhibou/agent/internal/model"
	"github.com/Buco7854/carhibou/agent/internal/store"
)

type agedPosition struct {
	fix *model.PositionFix
	age time.Duration
}

func (position agedPosition) Read() (*model.PositionFix, error) { return position.fix, nil }
func (position agedPosition) Age() time.Duration                { return position.age }

type freshPosition struct{ fix *model.PositionFix }

func (position freshPosition) Read() (*model.PositionFix, error) { return position.fix, nil }

func newAgent(t *testing.T, position PositionProvider) *Agent {
	t.Helper()
	queue, err := store.OpenQueue(t.TempDir() + "/queue.sqlite3")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = queue.Close() })
	return &Agent{Queue: queue, Position: position, Vehicle: EmptyVehicle{}, BootID: model.NewUUID()}
}

// A republished fix must be distinguishable from a freshly measured one, because
// the sample is stamped when it is taken rather than when the receiver saw it.
func TestCollectReportsHowOldAStreamedFixIs(t *testing.T) {
	fix := &model.PositionFix{Latitude: 48.8, Longitude: 2.3}
	agent := newAgent(t, agedPosition{fix: fix, age: 3200 * time.Millisecond})
	sample, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	age, present := sample.Agent["gps_fix_age_seconds"]
	if !present {
		t.Fatal("expected the fix age to travel with the sample")
	}
	if value, ok := age.(float64); !ok || value < 3.1 || value > 3.3 {
		t.Fatalf("gps_fix_age_seconds=%v, want about 3.2", age)
	}
	if sample.Position == nil {
		t.Fatal("expected an atomic position observation")
	}
	positionAge := sample.RecordedAt.Sub(sample.Position.ObservedAt)
	if positionAge < 3*time.Second || positionAge > 3400*time.Millisecond {
		t.Fatalf("position observed age=%s, want about 3.2s", positionAge)
	}
	if sample.Position.Channel != model.ChannelGNSS || sample.Position.Method != model.MethodDirect {
		t.Fatalf("position provenance=%s/%s", sample.Position.Channel, sample.Position.Method)
	}
}

// A polling source answers from the hardware every read, so there is no age to report.
func TestCollectOmitsFixAgeForAPollingSource(t *testing.T) {
	agent := newAgent(t, freshPosition{fix: &model.PositionFix{Latitude: 48.8, Longitude: 2.3}})
	sample, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if _, present := sample.Agent["gps_fix_age_seconds"]; present {
		t.Fatal("a polling source must not claim a fix age")
	}
}

func TestCollectOmitsFixAgeWithoutAPosition(t *testing.T) {
	agent := newAgent(t, agedPosition{fix: nil, age: time.Minute})
	sample, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if _, present := sample.Agent["gps_fix_age_seconds"]; present {
		t.Fatal("no position means there is no fix age to report")
	}
}

type failingVehicle struct{ reason string }

func (v failingVehicle) ReadObservations() (model.MetricObservations, error) {
	return model.MetricObservations{}, nil
}
func (v failingVehicle) Close()         {}
func (v failingVehicle) Status() string { return v.reason }

type switchingVehicle struct {
	observations model.MetricObservations
	live         bool
}

func (vehicle *switchingVehicle) ReadObservations() (model.MetricObservations, error) {
	return vehicle.observations, nil
}
func (vehicle *switchingVehicle) Close()     {}
func (vehicle *switchingVehicle) Live() bool { return vehicle.live }

// An agent whose adapter never connects still reports position and health, so
// without this the only evidence of a dead OBD path was the absence of metrics.
func TestCollectReportsWhyTheVehicleSourcePublishedNothing(t *testing.T) {
	agent := newAgent(t, EmptyPosition{})
	agent.Vehicle = failingVehicle{reason: "adapter did not connect: no such file"}

	sample, err := agent.Collect()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got := sample.Agent["vehicle_source_error"]; got != "adapter did not connect: no such file" {
		t.Fatalf("expected the failure in agent health, got %v", got)
	}

	agent.Vehicle = failingVehicle{}
	healthy, err := agent.Collect()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if _, present := healthy.Agent["vehicle_source_error"]; present {
		t.Fatal("a working source must not add an error field")
	}
}

func TestCollectDeclaresTheCadenceChosenForTheCurrentState(t *testing.T) {
	parked := newAgent(t, EmptyPosition{})
	parked.DrivingReportingInterval = 30
	parked.ParkedReportingInterval = 600
	parkedSample, err := parked.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if parkedSample.ReportingInterval == nil || *parkedSample.ReportingInterval != 600 {
		t.Fatalf("parked reporting interval=%v, want 600", parkedSample.ReportingInterval)
	}

	speed := 25.0
	driving := newAgent(t, freshPosition{fix: &model.PositionFix{Latitude: 48.8, Longitude: 2.3, Speed: &speed}})
	driving.DrivingReportingInterval = 30
	driving.ParkedReportingInterval = 600
	drivingSample, err := driving.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if drivingSample.ReportingInterval == nil || *drivingSample.ReportingInterval != 30 {
		t.Fatalf("driving reporting interval=%v, want 30", drivingSample.ReportingInterval)
	}
}

func TestCollectRetractsRememberedChannelKeysWhenTheProviderDies(t *testing.T) {
	now := time.Now().UTC()
	vehicle := &switchingVehicle{
		live: true,
		observations: model.MetricObservations{
			"vehicle.speed": {
				Value: 42.0,
				Metadata: model.ObservationMetadata{
					ObservedAt: now,
					Channel:    model.ChannelCAN,
					Method:     model.MethodDirect,
				},
			},
		},
	}
	agent := newAgent(t, EmptyPosition{})
	agent.Vehicle = vehicle
	if _, err := agent.Collect(); err != nil {
		t.Fatal(err)
	}
	vehicle.live = false
	vehicle.observations = model.MetricObservations{}
	retracted, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if len(retracted.Observations) != 1 || retracted.Observations[0].Value != nil {
		t.Fatalf("retractions=%#v, want one null observation", retracted.Observations)
	}
	if retracted.Observations[0].Key != "vehicle.speed" || retracted.Observations[0].Channel != model.ChannelCAN {
		t.Fatalf("wrong retraction provenance: %#v", retracted.Observations[0])
	}
}
