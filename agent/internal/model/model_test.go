package model

import (
	"encoding/json"
	"regexp"
	"strings"
	"testing"
	"time"
)

func TestNewUUID(t *testing.T) {
	value := NewUUID()
	if !regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`).MatchString(value) {
		t.Fatalf("invalid UUID: %s", value)
	}
}

func TestSampleUsesProtocolV2ObservationObjects(t *testing.T) {
	observedAt := time.Date(2026, 8, 29, 1, 2, 3, 0, time.UTC)
	sample := NewSample(1, &PositionObservation{
		Value: PositionFix{Latitude: 48.8, Longitude: 2.3}, ObservedAt: observedAt,
		Channel: ChannelGNSS, Method: MethodDirect,
	}, []Observation{{
		Key: "vehicle.speed", Value: 42.0, ObservedAt: observedAt,
		Channel: ChannelCAN, Method: MethodDirect,
	}}, nil)
	payload, err := json.Marshal(sample)
	if err != nil {
		t.Fatal(err)
	}
	text := string(payload)
	for _, required := range []string{`"observations":[`, `"key":"vehicle.speed"`, `"position":{"value":`, `"channel":"gnss"`} {
		if !strings.Contains(text, required) {
			t.Fatalf("payload %s does not contain %s", text, required)
		}
	}
	for _, legacy := range []string{`"metrics"`, `"metric_metadata"`, `"position_metadata"`} {
		if strings.Contains(text, legacy) {
			t.Fatalf("protocol-v2 payload contains legacy field %s: %s", legacy, text)
		}
	}
}
