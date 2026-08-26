package runtime

import (
	"math"
	"time"

	"github.com/Buco7854/vehinode/agent/internal/model"
)

// ActivitySource names the evidence that decided the vehicle's state.
//
// It travels with the sample because a tracker that has quietly dropped to its
// parked cadence looks identical to one whose adapter died, and the difference
// decides whether anything needs fixing.
type ActivitySource string

const (
	SourceReadiness ActivitySource = "readiness"
	SourceEngine    ActivitySource = "engine"
	SourceSpeed     ActivitySource = "speed"
	SourceMovement  ActivitySource = "movement"
	SourceIdle      ActivitySource = "idle"
	SourceGrace     ActivitySource = "grace"
)

// readinessMetrics are the canonical names that state outright whether the
// vehicle is in use. A profile declares one by decoding a frame to that name, so
// this needs no field in the profile format: the canonical name is the
// declaration. Charging counts as in use, because watching a charge is exactly
// when a slow cadence is least wanted.
//
// vehicle.ready covers a combustion vehicle with its ignition on and an electric
// one showing READY. There was a separate vehicle.ignition, treated identically
// in every respect, which is two names for one fact and a question anyone reading
// the list would have to ask.
//
// They are booleans on purpose. Vehicles do not agree on what their states are
// called — ready, run, IG1, accessory, crank — and an agent that had to recognise
// those names would need updating for every vehicle it met. A profile translates
// its own raw values into these three meanings and the agent recognises nothing
// else, so a vehicle nobody has seen before is a profile, not a release.
var readinessMetrics = []string{"vehicle.ready", "charging.active"}

const (
	// Below this a GPS fix is reporting its own noise rather than motion.
	movingKMH = 3.0
	// Far enough that no plausible run of stationary fixes explains it.
	movedMeters = 60.0
	// A vehicle at a light, a level crossing, or a drive-through is not parked.
	// Nothing below this holds the fast cadence on its own.
	DefaultActivityGrace = 3 * time.Minute
	earthRadiusMeters    = 6_371_000.0
)

// ActivityDetector decides whether the vehicle is in use.
//
// Sources are tried strongest first and each is allowed to fail: a vehicle whose
// profile decodes no readiness signal may still report engine speed, one with no
// adapter at all still has GPS speed, and a receiver that reports no speed field
// still has displacement. Only when every source is silent for the grace period
// does the vehicle count as parked.
type ActivityDetector struct {
	Grace        time.Duration
	lastEvidence time.Time
	anchor       *model.PositionFix
}

// Observe reports whether the vehicle is in use and what decided it.
func (detector *ActivityDetector) Observe(sample model.Sample, now time.Time) (bool, ActivitySource) {
	source, found := detector.evidence(sample)
	// The anchor is the place the vehicle was last seen. It has to be set while
	// parked too, or a tracker that starts up beside a parked car never has one,
	// and displacement — the only source left for a vehicle with no profile and a
	// receiver that reports no speed — can never fire. A sample without a fix
	// leaves the previous anchor alone rather than forgetting it.
	if sample.Position != nil && (found || detector.anchor == nil) {
		detector.anchor = sample.Position
	}
	if found {
		detector.lastEvidence = now
		return true, source
	}
	grace := detector.Grace
	if grace <= 0 {
		grace = DefaultActivityGrace
	}
	// A detector that has never seen evidence starts parked rather than holding
	// the fast cadence for one grace period every time the tracker restarts.
	if !detector.lastEvidence.IsZero() && now.Sub(detector.lastEvidence) < grace {
		return true, SourceGrace
	}
	return false, SourceIdle
}

func (detector *ActivityDetector) evidence(sample model.Sample) (ActivitySource, bool) {
	for _, name := range readinessMetrics {
		if value, present := sample.Metrics[name]; present {
			if truthy(value) {
				return SourceReadiness, true
			}
			// A readiness signal that says "off" is the strongest evidence there
			// is, so nothing weaker may overrule it. A car reporting ignition off
			// while its receiver drifts is parked. This is only reached for a
			// stated false: a raw value the profile does not map decodes to no
			// reading at all, so the vehicle is judged by the sources below it
			// rather than by a state nobody claimed.
			return SourceIdle, false
		}
	}
	// A turning engine is running, whatever else is silent. Only a positive
	// reading is evidence: zero covers a stop-start system at a light and every
	// electric vehicle, neither of which is parked.
	if rpm, ok := number(sample.Metrics["engine.rpm"]); ok && rpm > 0 {
		return SourceEngine, true
	}
	if speed, ok := number(sample.Metrics["vehicle.speed"]); ok && speed >= movingKMH {
		return SourceSpeed, true
	}
	if sample.Position != nil {
		if sample.Position.Speed != nil && *sample.Position.Speed >= movingKMH {
			return SourceSpeed, true
		}
		if detector.anchor != nil && distanceMeters(*detector.anchor, *sample.Position) >= movedMeters {
			return SourceMovement, true
		}
	}
	return SourceIdle, false
}

func truthy(value any) bool {
	switch typed := value.(type) {
	case bool:
		return typed
	case string:
		return typed == "true" || typed == "1" || typed == "on"
	default:
		numeric, ok := number(value)
		return ok && numeric != 0
	}
}

func number(value any) (float64, bool) {
	switch typed := value.(type) {
	case float64:
		return typed, true
	case float32:
		return float64(typed), true
	case int:
		return float64(typed), true
	case int64:
		return float64(typed), true
	case bool:
		if typed {
			return 1, true
		}
		return 0, true
	}
	return 0, false
}

func distanceMeters(from, to model.PositionFix) float64 {
	fromLat := from.Latitude * math.Pi / 180
	toLat := to.Latitude * math.Pi / 180
	deltaLat := toLat - fromLat
	deltaLon := (to.Longitude - from.Longitude) * math.Pi / 180
	sinLat := math.Sin(deltaLat / 2)
	sinLon := math.Sin(deltaLon / 2)
	a := sinLat*sinLat + math.Cos(fromLat)*math.Cos(toLat)*sinLon*sinLon
	return 2 * earthRadiusMeters * math.Asin(math.Min(1, math.Sqrt(a)))
}
