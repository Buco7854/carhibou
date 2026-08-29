package runtime

import (
	"errors"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Buco7854/carhibou/agent/internal/model"
)

type managedFakeVehicle struct {
	observations model.MetricObservations
	live         bool
	status       string
	state        string
	started      bool
	closed       int
	onStart      func(*managedFakeVehicle)
}

func (vehicle *managedFakeVehicle) Start() {
	vehicle.started = true
	if vehicle.onStart != nil {
		vehicle.onStart(vehicle)
	}
}
func (vehicle *managedFakeVehicle) ReadObservations() (model.MetricObservations, error) {
	return vehicle.observations, nil
}
func (vehicle *managedFakeVehicle) Close()         { vehicle.closed++ }
func (vehicle *managedFakeVehicle) Live() bool     { return vehicle.live }
func (vehicle *managedFakeVehicle) Status() string { return vehicle.status }
func (vehicle *managedFakeVehicle) State() string  { return vehicle.state }

func fastVehicleRetries(source *RetryingVehicleProvider) {
	source.mutex.Lock()
	defer source.mutex.Unlock()
	source.retryInitial = 5 * time.Millisecond
	source.retryMaximum = 20 * time.Millisecond
	source.backoff = source.retryInitial
	source.healthPoll = 5 * time.Millisecond
}

func waitFor(t *testing.T, condition func() bool) {
	t.Helper()
	deadline := time.Now().Add(time.Second)
	for !condition() {
		if time.Now().After(deadline) {
			t.Fatal("condition was not met before timeout")
		}
		time.Sleep(time.Millisecond)
	}
}

func TestRetryingVehicleProviderReportsMissingSourceInEverySample(t *testing.T) {
	source := NewRetryingVehicleProvider(func() (VehicleProvider, error) {
		return nil, errors.New("no OBD device found while probing serial candidates")
	})
	defer source.Close()
	agent := newAgent(t, EmptyPosition{})
	agent.Vehicle = source

	for sampleNumber := 0; sampleNumber < 2; sampleNumber++ {
		sample, err := agent.Collect()
		if err != nil {
			t.Fatal(err)
		}
		if len(sample.Observations) != 0 {
			t.Fatalf("sample %d observations=%#v, want none", sampleNumber, sample.Observations)
		}
		if got := sample.Agent["vehicle_source_error"]; got != "no OBD device found while probing serial candidates" {
			t.Fatalf("sample %d vehicle_source_error=%v", sampleNumber, got)
		}
	}
}

func TestRetryingVehicleProviderRecoversWhenDeviceAppears(t *testing.T) {
	now := time.Date(2026, 8, 29, 12, 0, 0, 0, time.UTC)
	vehicle := &managedFakeVehicle{
		live: true,
		observations: model.MetricObservations{
			"battery.soc": observation(67.0, now.Add(time.Second)),
		},
	}
	var available atomic.Bool
	source := NewRetryingVehicleProvider(func() (VehicleProvider, error) {
		if !available.Load() {
			return nil, errors.New("OBD adapter has not enumerated")
		}
		return vehicle, nil
	})
	fastVehicleRetries(source)
	defer source.Close()
	source.Start()
	agent := newAgent(t, EmptyPosition{})
	agent.Vehicle = source

	missing, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if got := missing.Agent["vehicle_source_error"]; got != "OBD adapter has not enumerated" {
		t.Fatalf("missing source error=%v", got)
	}

	available.Store(true)
	waitFor(t, func() bool { return source.Status() == "" && source.Live() })
	recovered, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if _, present := recovered.Agent["vehicle_source_error"]; present {
		t.Fatalf("recovered sample retained an error: %#v", recovered.Agent)
	}
	if len(recovered.Observations) != 1 || recovered.Observations[0].Key != "battery.soc" {
		t.Fatalf("recovered observations=%#v", recovered.Observations)
	}
	if !vehicle.started {
		t.Fatal("recovered provider was installed before it started")
	}
}

func TestRetryingVehicleProviderReportsProviderDeath(t *testing.T) {
	now := time.Date(2026, 8, 29, 12, 0, 0, 0, time.UTC)
	vehicle := &managedFakeVehicle{
		live: true,
		observations: model.MetricObservations{
			"vehicle.speed": observation(42.0, now),
		},
	}
	source := NewRetryingVehicleProvider(func() (VehicleProvider, error) { return vehicle, nil })
	defer source.Close()
	source.Start()
	agent := newAgent(t, EmptyPosition{})
	agent.Vehicle = source

	live, err := agent.Collect()
	if err != nil || len(live.Observations) != 1 {
		t.Fatalf("live sample=%#v, err=%v", live.Observations, err)
	}
	vehicle.live = false
	vehicle.status = "adapter stopped answering: input/output error"
	dead, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if got := dead.Agent["vehicle_source_error"]; got != vehicle.status {
		t.Fatalf("dead source error=%v", got)
	}
	if len(dead.Observations) != 1 || dead.Observations[0].Value != nil {
		t.Fatalf("dead source retractions=%#v", dead.Observations)
	}
	if vehicle.closed != 1 {
		t.Fatalf("dead provider close count=%d, want 1", vehicle.closed)
	}
}

func TestRetryingVehicleProviderReacquiresAfterBackgroundProviderDeath(t *testing.T) {
	now := time.Date(2026, 8, 29, 12, 0, 0, 0, time.UTC)
	first := &managedFakeVehicle{live: true}
	second := &managedFakeVehicle{
		live: true,
		observations: model.MetricObservations{
			"vehicle.speed": observation(23.0, now),
		},
	}
	var attempts atomic.Int32
	source := NewRetryingVehicleProvider(func() (VehicleProvider, error) {
		if attempts.Add(1) == 1 {
			return first, nil
		}
		return second, nil
	})
	fastVehicleRetries(source)
	defer source.Close()
	source.Start()

	source.mutex.Lock()
	first.live = false
	first.status = "vehicle adapter disappeared"
	source.mutex.Unlock()
	waitFor(t, func() bool { return source.Status() == "" && source.Live() && attempts.Load() >= 2 })

	agent := newAgent(t, EmptyPosition{})
	agent.Vehicle = source
	recovered, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if len(recovered.Observations) != 1 || recovered.Observations[0].Key != "vehicle.speed" {
		t.Fatalf("recovered observations=%#v", recovered.Observations)
	}
	if first.closed != 1 || !second.started {
		t.Fatalf("first closed=%d second started=%v", first.closed, second.started)
	}
}

func TestVehicleProviderStartsBeforeTheFirstRead(t *testing.T) {
	now := time.Date(2026, 8, 29, 12, 0, 0, 0, time.UTC)
	vehicle := &managedFakeVehicle{live: true}
	vehicle.onStart = func(started *managedFakeVehicle) {
		started.observations = model.MetricObservations{
			"battery.soc": observation(67.0, now),
		}
	}
	source := NewRetryingVehicleProvider(func() (VehicleProvider, error) { return vehicle, nil })
	defer source.Close()
	source.Start()
	if !vehicle.started {
		t.Fatal("vehicle provider was not started eagerly")
	}

	agent := newAgent(t, EmptyPosition{})
	agent.Vehicle = source
	first, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if len(first.Observations) != 1 || first.Observations[0].Key != "battery.soc" {
		t.Fatalf("first collected observations=%#v", first.Observations)
	}
}

func TestVehicleSourceStateIsPublishedWithoutBecomingAnError(t *testing.T) {
	vehicle := &managedFakeVehicle{
		live:  true,
		state: "unfiltered monitor; hardware filters ineffective",
	}
	source := NewRetryingVehicleProvider(func() (VehicleProvider, error) { return vehicle, nil })
	defer source.Close()
	source.Start()
	agent := newAgent(t, EmptyPosition{})
	agent.Vehicle = source

	sample, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if got := sample.Agent["vehicle_source_state"]; got != vehicle.state {
		t.Fatalf("vehicle_source_state=%v", got)
	}
	if _, present := sample.Agent["vehicle_source_error"]; present {
		t.Fatalf("degraded state was promoted to an error: %#v", sample.Agent)
	}
}
