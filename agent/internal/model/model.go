package model

import (
	"crypto/rand"
	"fmt"
	"sort"
	"time"
)

type PositionFix struct {
	Latitude   float64    `json:"latitude"`
	Longitude  float64    `json:"longitude"`
	Altitude   *float64   `json:"altitude,omitempty"`
	Speed      *float64   `json:"speed,omitempty"`
	Heading    *float64   `json:"heading,omitempty"`
	Accuracy   *float64   `json:"accuracy,omitempty"`
	RecordedAt *time.Time `json:"-"`
	FixQuality *int       `json:"-"`
	Satellites *int       `json:"-"`
}

const (
	ChannelCAN     = "can"
	ChannelOBD     = "obd"
	ChannelGNSS    = "gnss"
	ChannelMQTT    = "mqtt"
	ChannelDerived = "derived"
	MethodDirect   = "direct"
	MethodDerived  = "derived"
)

type ObservationMetadata struct {
	ObservedAt time.Time `json:"observed_at"`
	Channel    string    `json:"channel"`
	Method     string    `json:"method"`
}

type MetricObservation struct {
	Value    any
	Metadata ObservationMetadata
}

type MetricObservations map[string]MetricObservation

type Observation struct {
	Key        string    `json:"key"`
	Value      any       `json:"value"`
	ObservedAt time.Time `json:"observed_at"`
	Channel    string    `json:"channel"`
	Method     string    `json:"method"`
}

type PositionObservation struct {
	Value      PositionFix `json:"value"`
	ObservedAt time.Time   `json:"observed_at"`
	Channel    string      `json:"channel"`
	Method     string      `json:"method"`
}

func (observations MetricObservations) List() []Observation {
	result := make([]Observation, 0, len(observations))
	for key, observation := range observations {
		result = append(result, Observation{
			Key:        key,
			Value:      observation.Value,
			ObservedAt: observation.Metadata.ObservedAt,
			Channel:    observation.Metadata.Channel,
			Method:     observation.Metadata.Method,
		})
	}
	sort.Slice(result, func(left, right int) bool {
		if result[left].Key == result[right].Key {
			return result[left].Channel < result[right].Channel
		}
		return result[left].Key < result[right].Key
	})
	return result
}

type Sample struct {
	ID                string               `json:"id"`
	Sequence          int64                `json:"sequence"`
	RecordedAt        time.Time            `json:"recorded_at"`
	Position          *PositionObservation `json:"position,omitempty"`
	Observations      []Observation        `json:"observations"`
	Agent             map[string]any       `json:"agent"`
	ReportingInterval *int                 `json:"reporting_interval,omitempty"`
}

func NewSample(sequence int64, position *PositionObservation, observations []Observation, agent map[string]any) Sample {
	if observations == nil {
		observations = []Observation{}
	}
	return Sample{
		ID: NewUUID(), Sequence: sequence, RecordedAt: time.Now().UTC(), Position: position,
		Observations: observations, Agent: nonNilMap(agent),
	}
}

func (sample Sample) MetricValues() map[string]any {
	values := map[string]any{}
	for _, observation := range sample.Observations {
		values[observation.Key] = observation.Value
	}
	return values
}

func nonNilMap(value map[string]any) map[string]any {
	if value == nil {
		return map[string]any{}
	}
	return value
}

func NewUUID() string {
	var value [16]byte
	if _, err := rand.Read(value[:]); err != nil {
		panic(fmt.Sprintf("secure random UUID generation failed: %v", err))
	}
	value[6] = (value[6] & 0x0f) | 0x40
	value[8] = (value[8] & 0x3f) | 0x80
	return fmt.Sprintf("%08x-%04x-%04x-%04x-%012x",
		value[0:4], value[4:6], value[6:8], value[8:10], value[10:16])
}

type CANFrame struct {
	Timestamp float64 `json:"timestamp"`
	CANID     int     `json:"-"`
	Data      []byte  `json:"-"`
}
