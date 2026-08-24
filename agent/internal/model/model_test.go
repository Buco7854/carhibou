package model

import (
	"regexp"
	"testing"
)

func TestNewUUID(t *testing.T) {
	value := NewUUID()
	if !regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`).MatchString(value) {
		t.Fatalf("invalid UUID: %s", value)
	}
}
