package main

import (
	"os"
	"path/filepath"
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

// "config" without --pull must never need credentials or the network, because it
// is the first thing an operator runs on a tracker that cannot reach the server.
func TestConfigPrintsLocallyAndOnlyPullsWhenAsked(t *testing.T) {
	locations := paths{config: t.TempDir(), data: t.TempDir()}
	path := filepath.Join(locations.config, "config.json")
	if err := os.WriteFile(path, []byte(`{"version":4}`), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := commandConfig(locations, nil); err != nil {
		t.Fatalf("printing the local configuration failed: %v", err)
	}
	err := commandConfig(locations, []string{"--pull"})
	if err == nil {
		t.Fatal("expected --pull to need credentials")
	}
	if strings.Contains(err.Error(), "flag provided but not defined") {
		t.Fatalf("--pull is not accepted: %v", err)
	}
}
