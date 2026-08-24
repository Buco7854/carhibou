package model

import (
	"crypto/rand"
	"fmt"
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

type Sample struct {
	ID         string         `json:"id"`
	Sequence   int64          `json:"sequence"`
	RecordedAt time.Time      `json:"recorded_at"`
	Position   *PositionFix   `json:"position"`
	Metrics    map[string]any `json:"metrics"`
	Device     map[string]any `json:"device"`
}

func NewSample(sequence int64, position *PositionFix, metrics, device map[string]any) Sample {
	return Sample{
		ID: NewUUID(), Sequence: sequence, RecordedAt: time.Now().UTC(), Position: position,
		Metrics: nonNilMap(metrics), Device: nonNilMap(device),
	}
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
