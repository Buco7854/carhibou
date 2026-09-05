package runtime

import (
	"errors"
	"testing"
	"time"

	"github.com/Buco7854/carhibou/agent/internal/client"
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

type changingPosition struct{ fix *model.PositionFix }

func (position *changingPosition) Read() (*model.PositionFix, error) { return position.fix, nil }

func newAgent(t *testing.T, position PositionProvider) *Agent {
	t.Helper()
	queue, err := store.OpenQueue(t.TempDir() + "/queue.sqlite3")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = queue.Close() })
	return &Agent{Queue: queue, Position: position, Vehicle: EmptyVehicle{}, BootID: model.NewUUID()}
}

type recordingTelemetryClient struct {
	batches     [][]model.Sample
	failRequest int
}

func (client *recordingTelemetryClient) Upload(_ string, samples []model.Sample) ([]string, error) {
	batch := append([]model.Sample(nil), samples...)
	client.batches = append(client.batches, batch)
	if client.failRequest == len(client.batches) {
		return nil, errors.New("network unavailable")
	}
	acknowledged := make([]string, 0, len(samples))
	for _, sample := range samples {
		acknowledged = append(acknowledged, sample.ID)
	}
	return acknowledged, nil
}

func TestUploadRetainsTheFailedChunkAndEverythingAfterIt(t *testing.T) {
	agent := newAgent(t, EmptyPosition{})
	transport := &recordingTelemetryClient{failRequest: 2}
	agent.Client = transport
	for sequence := int64(1); sequence <= 450; sequence++ {
		if err := agent.Queue.Enqueue(model.NewSample(sequence, nil, nil, nil)); err != nil {
			t.Fatal(err)
		}
	}

	uploaded, err := agent.Upload(nil)
	if err == nil || uploaded != 200 {
		t.Fatalf("first flush uploaded=%d, error=%v; want 200 and the network error", uploaded, err)
	}
	depth, err := agent.Queue.Depth()
	if err != nil || depth != 250 {
		t.Fatalf("queue depth=%d, want 250 after the failed request (error=%v)", depth, err)
	}

	transport.failRequest = 0
	uploaded, err = agent.Upload(nil)
	if err != nil || uploaded != 250 {
		t.Fatalf("retry uploaded=%d, want 250 (error=%v)", uploaded, err)
	}
	depth, err = agent.Queue.Depth()
	if err != nil || depth != 0 {
		t.Fatalf("queue depth=%d, want 0 after retry (error=%v)", depth, err)
	}
}

func TestUploadFlushesALargeOutboxInBoundedRequests(t *testing.T) {
	agent := newAgent(t, EmptyPosition{})
	transport := &recordingTelemetryClient{}
	agent.Client = transport
	for sequence := int64(1); sequence <= 650; sequence++ {
		sample := model.NewSample(sequence, nil, nil, map[string]any{"sequence": sequence})
		if err := agent.Queue.Enqueue(sample); err != nil {
			t.Fatal(err)
		}
	}

	uploaded, err := agent.Upload(nil)
	if err != nil {
		t.Fatal(err)
	}
	if uploaded != 650 {
		t.Fatalf("uploaded=%d, want 650", uploaded)
	}

	wantSizes := []int{200, 200, 200, 50}
	if len(transport.batches) != len(wantSizes) {
		t.Fatalf("requests=%d, want %d", len(transport.batches), len(wantSizes))
	}
	var sequence int64
	for index, batch := range transport.batches {
		if len(batch) != wantSizes[index] {
			t.Fatalf("request %d has %d samples, want %d", index+1, len(batch), wantSizes[index])
		}
		for _, sample := range batch {
			sequence++
			if sample.Sequence != sequence {
				t.Fatalf("sample sequence=%d, want %d", sample.Sequence, sequence)
			}
		}
	}
	depth, err := agent.Queue.Depth()
	if err != nil || depth != 0 {
		t.Fatalf("queue depth=%d, want 0 (error=%v)", depth, err)
	}
}

// countingTelemetryClient records how many chunks the drain has sent, which is
// what a heartbeat has to interleave with.
type countingTelemetryClient struct {
	uploads int
}

func (client *countingTelemetryClient) Upload(_ string, samples []model.Sample) ([]string, error) {
	client.uploads++
	acknowledged := make([]string, 0, len(samples))
	for _, sample := range samples {
		acknowledged = append(acknowledged, sample.ID)
	}
	return acknowledged, nil
}

// A backlog drains in chunks and each one is a request that can spend its whole
// timeout, so the heartbeat has to come between them rather than after the drain
// finishes, or a long catch-up starves the loop watchdog.
//
// The evidence is which chunk each heartbeat follows, not how many milliseconds
// apart they were. The wall-clock form of this test measured the machine rather
// than the code and failed on a loaded CI runner at 127 ms against a 100 ms
// bound, while the guarantee it was trying to state is exact: one heartbeat per
// chunk, in step with them.
func TestCatchUpUploadRefreshesHeartbeatBetweenChunks(t *testing.T) {
	const chunks = 10
	agent := newAgent(t, EmptyPosition{})
	transport := &countingTelemetryClient{}
	agent.Client = transport
	for sequence := int64(1); sequence <= chunks*client.MaxTelemetryBatchSize; sequence++ {
		if err := agent.Queue.Enqueue(model.NewSample(sequence, nil, nil, nil)); err != nil {
			t.Fatal(err)
		}
	}

	chunksSent := []int{}
	uploaded, err := agent.Upload(func() { chunksSent = append(chunksSent, transport.uploads) })
	if err != nil || uploaded != chunks*client.MaxTelemetryBatchSize {
		t.Fatalf("uploaded=%d err=%v", uploaded, err)
	}
	if len(chunksSent) != chunks {
		t.Fatalf("heartbeats=%d, want one after each full chunk", len(chunksSent))
	}
	for index, sent := range chunksSent {
		if sent != index+1 {
			t.Fatalf("heartbeat %d came after %d chunks, want exactly one chunk between heartbeats",
				index+1, sent)
		}
	}
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
	detached     bool
}

func (vehicle *switchingVehicle) ReadObservations() (model.MetricObservations, error) {
	return vehicle.observations, nil
}
func (vehicle *switchingVehicle) Close()         {}
func (vehicle *switchingVehicle) Live() bool     { return vehicle.live }
func (vehicle *switchingVehicle) Attached() bool { return !vehicle.detached }

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
	position := &changingPosition{}
	agent := newAgent(t, position)
	agent.DrivingReportingInterval = 30
	agent.ParkedReportingInterval = 600
	parkedSample, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if parkedSample.ReportingInterval == nil || *parkedSample.ReportingInterval != 600 {
		t.Fatalf("parked reporting interval=%v, want 600", parkedSample.ReportingInterval)
	}

	speed := 25.0
	position.fix = &model.PositionFix{Latitude: 48.8, Longitude: 2.3, Speed: &speed}
	drivingSample, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if drivingSample.ReportingInterval == nil || *drivingSample.ReportingInterval != 30 {
		t.Fatalf("driving reporting interval=%v, want 30", drivingSample.ReportingInterval)
	}
}

func observation(value any, observedAt time.Time) model.MetricObservation {
	return model.MetricObservation{
		Value: value,
		Metadata: model.ObservationMetadata{
			ObservedAt: observedAt,
			Channel:    model.ChannelCAN,
			Method:     model.MethodDirect,
		},
	}
}

func TestCollectOnlyEmitsMetricObservationsWhoseTimestampAdvanced(t *testing.T) {
	firstObservedAt := time.Now().UTC()
	vehicle := &switchingVehicle{
		live: true,
		observations: model.MetricObservations{
			"battery.soc": observation(67.0, firstObservedAt),
		},
	}
	agent := newAgent(t, EmptyPosition{})
	agent.Vehicle = vehicle

	first, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if len(first.Observations) != 1 {
		t.Fatalf("first observations=%#v, want the current snapshot", first.Observations)
	}
	vehicle.observations["battery.soc"] = observation(68.0, firstObservedAt)
	frozen, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if len(frozen.Observations) != 0 {
		t.Fatalf("frozen cache was republished: %#v", frozen.Observations)
	}

	secondObservedAt := firstObservedAt.Add(time.Second)
	vehicle.observations["battery.soc"] = observation(67.0, secondObservedAt)
	confirmed, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if len(confirmed.Observations) != 1 || !confirmed.Observations[0].ObservedAt.Equal(secondObservedAt) {
		t.Fatalf("fresh confirmation was suppressed: %#v", confirmed.Observations)
	}
}

func TestCollectOnlyEmitsPositionWhenItsTimestampAdvanced(t *testing.T) {
	firstObservedAt := time.Now().UTC()
	position := &changingPosition{fix: &model.PositionFix{
		Latitude: 48.8, Longitude: 2.3, RecordedAt: &firstObservedAt,
	}}
	agent := newAgent(t, position)

	first, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if first.Position == nil {
		t.Fatal("first position snapshot was suppressed")
	}
	frozen, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if frozen.Position != nil {
		t.Fatalf("frozen position was republished: %#v", frozen.Position)
	}

	secondObservedAt := firstObservedAt.Add(time.Second)
	position.fix.RecordedAt = &secondObservedAt
	confirmed, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if confirmed.Position == nil || !confirmed.Position.ObservedAt.Equal(secondObservedAt) {
		t.Fatalf("fresh position confirmation was suppressed: %#v", confirmed.Position)
	}
}

func TestFreshAgentResendsAProvidersCurrentSnapshot(t *testing.T) {
	vehicle := &switchingVehicle{
		live: true,
		observations: model.MetricObservations{
			"battery.soc": observation(67.0, time.Now().UTC()),
		},
	}
	firstAgent := newAgent(t, EmptyPosition{})
	firstAgent.Vehicle = vehicle
	if first, err := firstAgent.Collect(); err != nil || len(first.Observations) != 1 {
		t.Fatalf("first agent snapshot=%#v, err=%v", first.Observations, err)
	}

	restartedAgent := newAgent(t, EmptyPosition{})
	restartedAgent.Vehicle = vehicle
	restarted, err := restartedAgent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if len(restarted.Observations) != 1 {
		t.Fatalf("fresh agent suppressed current snapshot: %#v", restarted.Observations)
	}
}

// A sleeping vehicle stops broadcasting while its adapter keeps answering. The
// values it last reported are still true of it, so nothing is retracted and the
// server is left to age them under its own freshness rules. Retracting here is
// what made a parked car's odometer and state of charge vanish overnight.
type eventingVehicle struct {
	observations model.MetricObservations
	event        string
}

func (vehicle *eventingVehicle) ReadObservations() (model.MetricObservations, error) {
	return vehicle.observations, nil
}
func (vehicle *eventingVehicle) Close() {}
func (vehicle *eventingVehicle) TakeEvent() string {
	reason := vehicle.event
	vehicle.event = ""
	return reason
}

// An event sample is a bonus delivery. It says why it arrived early and leaves
// the declared cadence alone, because the promise the server judges freshness
// against is about the next ordinary delivery, not this one.
// A vehicle with no OBD hardware at all is still a vehicle worth tracking. The
// position path must not depend on a vehicle source existing.
func TestGNSSOnlyVehicleStillProducesCompleteSamples(t *testing.T) {
	fix := &model.PositionFix{Latitude: 48.85, Longitude: 2.35}
	agent := newAgent(t, freshPosition{fix: fix})
	agent.Vehicle = EmptyVehicle{}
	sample, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if sample.Position == nil {
		t.Fatal("a GNSS-only agent must still report position")
	}
	if len(sample.Observations) != 0 {
		t.Fatalf("no vehicle source, yet observations=%#v", sample.Observations)
	}
	if _, reported := sample.Agent["vehicle_source_error"]; reported {
		t.Fatal("having no vehicle source is not an error to report")
	}
	if _, present := sample.Agent["hostname"]; !present {
		t.Fatal("health must travel with every sample")
	}
}

// A profile assigned to a car that is asleep: the adapter is attached, the bus
// says nothing, and the agent keeps reporting honestly rather than falling
// silent or retracting.
func TestSleepingProfiledVehicleKeepsHeartbeatingWithAnHonestStatus(t *testing.T) {
	vehicle := &statefulVehicle{
		state: "monitoring, bus quiet for 8h0m0s",
		observations: model.MetricObservations{
			"battery.aux_voltage": observation(12.4, time.Now().UTC()),
		},
	}
	agent := newAgent(t, EmptyPosition{})
	agent.Vehicle = vehicle
	first, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if len(first.Observations) != 1 || first.Observations[0].Key != "battery.aux_voltage" {
		t.Fatalf("observations=%#v, want the supply reading", first.Observations)
	}
	if first.Agent["vehicle_source_state"] != vehicle.state {
		t.Fatalf("vehicle_source_state=%v, want %q", first.Agent["vehicle_source_state"], vehicle.state)
	}
	if _, reported := first.Agent["vehicle_source_error"]; reported {
		t.Fatal("a sleeping bus is not an error")
	}
	second, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if len(second.Observations) != 0 {
		t.Fatalf("unchanged supply reading was republished: %#v", second.Observations)
	}
	if second.Agent["vehicle_source_state"] != vehicle.state {
		t.Fatal("the heartbeat stopped explaining itself")
	}
}

type statefulVehicle struct {
	observations model.MetricObservations
	state        string
}

func (vehicle *statefulVehicle) ReadObservations() (model.MetricObservations, error) {
	return vehicle.observations, nil
}
func (vehicle *statefulVehicle) Close()         {}
func (vehicle *statefulVehicle) State() string  { return vehicle.state }
func (vehicle *statefulVehicle) Attached() bool { return true }

func TestEventSampleIsStampedWithoutChangingTheCadencePromise(t *testing.T) {
	vehicle := &eventingVehicle{observations: model.MetricObservations{}}
	agent := newAgent(t, EmptyPosition{})
	agent.Vehicle = vehicle
	agent.DrivingReportingInterval = 30
	agent.ParkedReportingInterval = 600

	if reason := agent.PendingEvent(); reason != "" {
		t.Fatalf("unprompted event: %q", reason)
	}
	ordinary, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if _, stamped := ordinary.Agent["sample_trigger"]; stamped {
		t.Fatal("a cadence sample must not claim a trigger")
	}

	vehicle.event = "charging.active changed to true"
	reason := agent.PendingEvent()
	if reason == "" {
		t.Fatal("expected the transition to be reported")
	}
	triggered, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if triggered.Agent["sample_trigger"] != reason {
		t.Fatalf("sample_trigger=%v, want %q", triggered.Agent["sample_trigger"], reason)
	}
	if triggered.ReportingInterval == nil || *triggered.ReportingInterval != 600 {
		t.Fatalf("reporting interval=%v, want the parked cadence unchanged", triggered.ReportingInterval)
	}
	next, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if _, stamped := next.Agent["sample_trigger"]; stamped {
		t.Fatal("the trigger outlived the sample it explained")
	}
}

func TestQuietBusRetractsNothingAndStaysSilent(t *testing.T) {
	vehicle := &switchingVehicle{
		live: true,
		observations: model.MetricObservations{
			"vehicle.odometer": observation(48211.0, time.Now().UTC()),
		},
	}
	agent := newAgent(t, EmptyPosition{})
	agent.Vehicle = vehicle
	first, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if len(first.Observations) != 1 {
		t.Fatalf("first sample=%#v, want the odometer", first.Observations)
	}

	// The bus goes quiet: no new frames, so no advancing timestamps, but the
	// adapter is still there.
	vehicle.live = false
	for round := 0; round < 3; round++ {
		quiet, err := agent.Collect()
		if err != nil {
			t.Fatal(err)
		}
		if len(quiet.Observations) != 0 {
			t.Fatalf("quiet bus published %#v, want silence", quiet.Observations)
		}
	}

	// And when it wakes, the same cached value is not resent until it advances.
	vehicle.live = true
	woken, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if len(woken.Observations) != 0 {
		t.Fatalf("waking republished an unchanged value: %#v", woken.Observations)
	}
}

func TestCollectRetractsCachedChannelValuesOnceAndResumesAfterRevival(t *testing.T) {
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
	live, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if len(live.Observations) != 1 || live.Observations[0].Value != 42.0 {
		t.Fatalf("live observations=%#v, want the cached value", live.Observations)
	}
	suppressed, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if len(suppressed.Observations) != 0 {
		t.Fatalf("cached observation was republished: %#v", suppressed.Observations)
	}
	vehicle.detached = true
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
	dead, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if len(dead.Observations) != 0 {
		t.Fatalf("dead provider republished its cache: %#v", dead.Observations)
	}

	vehicle.detached = false
	revived, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if len(revived.Observations) != 1 || revived.Observations[0].Value != 42.0 {
		t.Fatalf("revived observations=%#v, want the cached value again", revived.Observations)
	}
}

// The evening that prompted the ruling: a C-Zero plugged in at home uploaded
// every fifteen seconds until it was full, because the charge was counted as
// use. A charging car is a parked car, and parked cadence is what it gets.
func TestAChargingVehicleKeepsTheParkedCadence(t *testing.T) {
	now := time.Now().UTC()
	vehicle := &switchingVehicle{
		live: true,
		observations: model.MetricObservations{
			"charging.active": observation(true, now),
			"charging.power":  observation(3.2, now),
			"battery.soc":     observation(64.0, now),
		},
	}
	agent := newAgent(t, EmptyPosition{})
	agent.Vehicle = vehicle
	agent.DrivingReportingInterval = 15
	agent.ParkedReportingInterval = 600

	sample, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if sample.Agent["vehicle_in_use"] != false {
		t.Fatalf("vehicle_in_use=%v, want a charging car parked", sample.Agent["vehicle_in_use"])
	}
	if sample.Agent["activity_source"] != string(SourceIdle) {
		t.Fatalf("activity_source=%v, want %q", sample.Agent["activity_source"], SourceIdle)
	}
	if sample.ReportingInterval == nil || *sample.ReportingInterval != 600 {
		t.Fatalf("reporting interval=%v, want the parked cadence", sample.ReportingInterval)
	}
	if agent.InUse {
		t.Fatal("a charging vehicle must not hold the agent in use")
	}
}
