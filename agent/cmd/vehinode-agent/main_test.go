package main

import (
	"strings"
	"testing"
)

func TestCommandsRejectNonPositiveDurations(t *testing.T) {
	tests := [][]string{
		{"gps-info", "--seconds", "0"},
		{"can-record", "--seconds", "-1", "capture.jsonl"},
		{"run", "--config-sync-seconds", "0"},
	}
	for _, arguments := range tests {
		if err := execute(arguments); err == nil || !strings.Contains(err.Error(), "greater than zero") {
			t.Fatalf("execute(%v) error = %v", arguments, err)
		}
	}
}
