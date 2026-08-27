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

func (v failingVehicle) ReadMetrics() (map[string]any, error) { return map[string]any{}, nil }
func (v failingVehicle) Close()                               {}
func (v failingVehicle) Status() string                       { return v.reason }

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
