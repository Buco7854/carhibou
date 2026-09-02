package runtime

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/Buco7854/carhibou/agent/internal/client"
	"github.com/Buco7854/carhibou/agent/internal/model"
	"github.com/Buco7854/carhibou/agent/internal/store"
)

type PositionProvider interface {
	Read() (*model.PositionFix, error)
}

// AgedPosition is implemented by a source that can republish an unchanged fix.
// Both supported sources can: a stream goes quiet, and a cellular module keeps
// answering from its last known position after the receiver stops tracking.
type AgedPosition interface {
	Age() time.Duration
}

// PositionStatus and PositionState mirror the vehicle-source pair. A position
// source fails in exactly the ways a vehicle source does — no device, a port that
// will not open, a receiver that went quiet — and until it could say so a vehicle
// that stopped reporting its position was indistinguishable from one parked in a
// tunnel. Read returns what it has rather than an error, so the explanation has
// to travel separately.
// PositionPoll is implemented by a source whose current fix can be taken as
// often as anyone likes, because reading it costs a buffer drain rather than a
// command exchange. A modem answering +CGPSINFO is not one of these: asking it
// four times a second would spend the whole interval on the serial line.
type PositionPoll interface {
	PollFix() (*model.PositionFix, error)
}

type PositionStatus interface {
	Status() string
}

type PositionState interface {
	State() string
}

type VehicleProvider interface {
	ReadObservations() (model.MetricObservations, error)
	Close()
}

// VehicleStarter lets a source acquire its hardware and begin any background
// monitoring before the first sample is taken. ReadObservations remains a safe
// fallback for callers that do not manage provider lifecycles explicitly.
type VehicleStarter interface {
	Start()
}

// VehicleStatus is implemented by a source that can say why it published no
// metrics. Every fault reading a vehicle is recoverable and none of them should
// stop an agent reporting its position, so ReadMetrics returns what it has
// rather than an error. Without this a dead adapter is indistinguishable from a
// vehicle that simply has nothing to report.
type VehicleStatus interface {
	Status() string
}

type VehicleState interface {
	State() string
}

type VehicleLiveness interface {
	Live() bool
}

// VehicleAttachment separates hardware that has gone away from a vehicle that
// has gone to sleep.
//
// Both stop producing frames and neither can be told from the other by the
// decoded values, but they mean opposite things. An adapter that is gone can no
// longer vouch for anything it reported, so those values stop being
// observations. A vehicle asleep on the driveway is still the vehicle the last
// reading described: its odometer did not become unknown because its CAN bus
// stopped broadcasting overnight.
type VehicleAttachment interface {
	Attached() bool
}

// VehicleEvents is implemented by a source that notices a state change between
// samples. Waiting out a parked cadence to report that a charge started is how a
// plug-in at 02:00 first appears at 02:10; the source sees the transition when
// it decodes it, so it says so and the caller takes a sample early.
type VehicleEvents interface {
	TakeEvent() string
}

type EmptyPosition struct{}

func (EmptyPosition) Read() (*model.PositionFix, error) { return nil, nil }

type EmptyVehicle struct{}

func (EmptyVehicle) ReadObservations() (model.MetricObservations, error) {
	return model.MetricObservations{}, nil
}
func (EmptyVehicle) Close() {}

type rememberedVehicleKey struct {
	method     string
	observedAt time.Time
}

type Agent struct {
	Queue    *store.Queue
	Client   *client.Client
	Position PositionProvider
	Vehicle  VehicleProvider
	BootID   string
	Sequence int64
	Activity ActivityDetector
	// InUse is what the last Collect decided, so the caller can choose the
	// interval it waits before the next one.
	InUse                    bool
	DrivingReportingInterval int
	ParkedReportingInterval  int
	vehicleKeys              map[string]map[string]rememberedVehicleKey
	positionObservedAt       *time.Time
	eventReason              string
	motionAnchor             *model.PositionFix
	motionAnchoredAt         time.Time
	motionReportedAt         time.Time
}

const (
	// motionOnsetMeters is how far a parked vehicle must be seen to have gone
	// before its own displacement is called a departure. Far enough that a fix
	// wandering under cover cannot reach it, near enough that a car pulling away
	// crosses it within seconds.
	motionOnsetMeters = 150.0
	// motionAnchorWindow bounds how long displacement is measured over, so slow
	// drift cannot accumulate into a departure across a ten-minute parked gap.
	motionAnchorWindow = time.Minute
	// motionReportGap keeps a vehicle crossing the threshold repeatedly from
	// asking for a sample each time.
	motionReportGap = 30 * time.Second
)

// PendingEvent reports a state change that deserves a sample before the next
// cadence deadline, consuming it so one transition causes one sample.
func (agent *Agent) PendingEvent() string {
	events, ok := agent.Vehicle.(VehicleEvents)
	if !ok {
		return ""
	}
	reason := events.TakeEvent()
	if reason != "" {
		agent.eventReason = reason
	}
	return reason
}

// MotionEvent notices a parked vehicle leaving, for a source that has no speed
// to read.
//
// A vehicle with no profile, or one whose profile decodes no speed, is invisible
// between samples: the only evidence it has left is that it is no longer where it
// was, and on a parked cadence nobody looks for ten minutes. This is checked far
// more often than a sample is taken, so departure is noticed in the seconds it
// takes to cover the threshold rather than at the next deadline.
func (agent *Agent) MotionEvent(now time.Time) string {
	// A vehicle already known to be in use is on the fast cadence; there is
	// nothing here for it to discover.
	if agent.InUse {
		return ""
	}
	poller, ok := agent.Position.(PositionPoll)
	if !ok {
		return ""
	}
	fix, err := poller.PollFix()
	if err != nil || fix == nil {
		return ""
	}
	current := *fix
	if agent.motionAnchor == nil || now.Sub(agent.motionAnchoredAt) > motionAnchorWindow {
		agent.motionAnchor = &current
		agent.motionAnchoredAt = now
		return ""
	}
	moved := distanceMeters(*agent.motionAnchor, current)
	if moved < motionOnsetMeters || moved < reportedAccuracy(current) {
		return ""
	}
	agent.motionAnchor = &current
	agent.motionAnchoredAt = now
	if !agent.motionReportedAt.IsZero() && now.Sub(agent.motionReportedAt) < motionReportGap {
		return ""
	}
	agent.motionReportedAt = now
	reason := fmt.Sprintf("vehicle moved %.0f m while parked", moved)
	agent.eventReason = reason
	return reason
}

func (agent *Agent) Collect() (model.Sample, error) {
	position, _ := agent.Position.Read()
	observations, _ := agent.Vehicle.ReadObservations()
	if agent.vehicleKeys == nil {
		agent.vehicleKeys = map[string]map[string]rememberedVehicleKey{}
	}
	// Only the death of the channel retracts. Frame silence does not: a bus that
	// sleeps every night would otherwise retract the vehicle's odometer and state
	// of charge at the same time every night, and the server would forget values
	// it is supposed to keep and mark stale. Silence is left to age out under the
	// freshness rules; a channel that has actually gone says so.
	channelDead := false
	if reporter, ok := agent.Vehicle.(VehicleStatus); ok && reporter.Status() != "" {
		channelDead = true
	}
	if attachment, ok := agent.Vehicle.(VehicleAttachment); ok && !attachment.Attached() {
		channelDead = true
	}
	if channelDead {
		// A provider may retain its last decoded values for diagnostics and for a
		// quick recovery. Once it reports dead, those cached values are no longer
		// observations: publish the remembered retractions once, then stay silent
		// until the provider reports live again.
		observations = model.MetricObservations{}
		now := time.Now().UTC()
		for channel, keys := range agent.vehicleKeys {
			for key, remembered := range keys {
				observations[key] = model.MetricObservation{
					Value: nil,
					Metadata: model.ObservationMetadata{
						ObservedAt: now, Channel: channel, Method: remembered.method,
					},
				}
			}
		}
		agent.vehicleKeys = map[string]map[string]rememberedVehicleKey{}
	} else {
		advanced := model.MetricObservations{}
		for key, observation := range observations {
			channel := observation.Metadata.Channel
			if agent.vehicleKeys[channel] == nil {
				agent.vehicleKeys[channel] = map[string]rememberedVehicleKey{}
			}
			remembered, reported := agent.vehicleKeys[channel][key]
			remembered.method = observation.Metadata.Method
			if !reported || observation.Metadata.ObservedAt.After(remembered.observedAt) {
				advanced[key] = observation
				remembered.observedAt = observation.Metadata.ObservedAt
			}
			agent.vehicleKeys[channel][key] = remembered
		}
		observations = advanced
	}
	depth, _ := agent.Queue.Depth()
	health := SystemHealth(depth)
	// A sample is stamped when it is taken, but a streaming receiver may have
	// published its fix slightly earlier. Reporting that gap keeps a repeated
	// position distinguishable from a freshly measured one.
	if aged, ok := agent.Position.(AgedPosition); ok && position != nil {
		// One decimal is the useful precision for a staleness figure; the rest is
		// noise that widens every column showing it.
		health["gps_fix_age_seconds"] = float64(aged.Age()/(100*time.Millisecond)) / 10
	}
	if reporter, ok := agent.Position.(PositionStatus); ok {
		if status := reporter.Status(); status != "" {
			health["position_source_error"] = status
		}
	}
	if reporter, ok := agent.Position.(PositionState); ok {
		if state := reporter.State(); state != "" {
			health["position_source_state"] = state
		}
	}
	if reporter, ok := agent.Vehicle.(VehicleStatus); ok {
		if status := reporter.Status(); status != "" {
			health["vehicle_source_error"] = status
		}
	}
	if reporter, ok := agent.Vehicle.(VehicleState); ok {
		if state := reporter.State(); state != "" {
			health["vehicle_source_state"] = state
		}
	}
	var positionObservation *model.PositionObservation
	if position != nil {
		observedAt := time.Now().UTC()
		if position.RecordedAt != nil {
			observedAt = position.RecordedAt.UTC()
		} else if aged, ok := agent.Position.(AgedPosition); ok {
			observedAt = observedAt.Add(-aged.Age())
		}
		if agent.positionObservedAt == nil || observedAt.After(*agent.positionObservedAt) {
			positionObservation = &model.PositionObservation{
				Value:      *position,
				ObservedAt: observedAt,
				Channel:    model.ChannelGNSS,
				Method:     model.MethodDirect,
			}
			agent.positionObservedAt = &observedAt
		}
	}
	sample := model.NewSample(agent.Sequence+1, positionObservation, observations.List(), health)
	inUse, source := agent.Activity.Observe(sample, time.Now())
	agent.InUse = inUse
	reportingInterval := agent.ParkedReportingInterval
	if inUse {
		reportingInterval = agent.DrivingReportingInterval
	}
	if reportingInterval > 0 {
		sample.ReportingInterval = &reportingInterval
	}
	// Published because an agent that has dropped to its parked cadence is
	// otherwise indistinguishable from one whose hardware stopped answering.
	sample.Agent["vehicle_in_use"] = inUse
	sample.Agent["activity_source"] = string(source)
	// An event sample is a bonus delivery, not a new promise: the declared
	// interval above still describes the cadence, and this only says why one
	// sample arrived early.
	if agent.eventReason != "" {
		sample.Agent["sample_trigger"] = agent.eventReason
		agent.eventReason = ""
	}
	agent.Sequence++
	return sample, agent.Queue.Enqueue(sample)
}

func (agent *Agent) Upload(limit int) (int64, error) {
	samples, err := agent.Queue.Pending(limit)
	if err != nil || len(samples) == 0 {
		return 0, err
	}
	acknowledged, err := agent.Client.Upload(agent.BootID, samples)
	if err != nil {
		return 0, err
	}
	return agent.Queue.Acknowledge(acknowledged)
}

func SystemHealth(queueDepth int) map[string]any {
	hostname, _ := os.Hostname()
	result := map[string]any{"hostname": hostname, "queue_depth": queueDepth}
	if source, err := os.Open("/proc/loadavg"); err == nil {
		scanner := bufio.NewScanner(source)
		scanner.Split(bufio.ScanWords)
		if scanner.Scan() {
			if value, err := strconv.ParseFloat(scanner.Text(), 64); err == nil {
				result["load_1m"] = value
			}
		}
		source.Close()
	}
	if content, err := os.ReadFile("/sys/class/thermal/thermal_zone0/temp"); err == nil {
		if value, err := strconv.ParseFloat(strings.TrimSpace(string(content)), 64); err == nil {
			result["cpu_temperature"] = float64(int(value/100)) / 10
		}
	}
	return result
}

func LastSequence(queue *store.Queue) (int64, error) {
	return queue.LastSequence()
}

func ValidateDistinctDevices(gps, obd string) error {
	if gps == "" || obd == "" {
		return nil
	}
	gpsPath, gpsErr := filepath.EvalSymlinks(gps)
	if gpsErr != nil {
		gpsPath = filepath.Clean(gps)
	}
	obdPath, obdErr := filepath.EvalSymlinks(obd)
	if obdErr != nil {
		obdPath = filepath.Clean(obd)
	}
	if gpsPath == obdPath {
		return fmt.Errorf("GPS and OBD cannot use the same serial device")
	}
	return nil
}
