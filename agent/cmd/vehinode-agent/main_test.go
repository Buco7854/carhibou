package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/Buco7854/vehinode/agent/internal/providers"
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

// A port the sweep already classified must not be reopened. Reopening one this
// process had just closed wedged the SIM7600's USB serial driver and hung every
// diagnostic command after the sweep finished printing.
func TestResolveReusesTheSweepRatherThanReprobing(t *testing.T) {
	nmea := "/dev/serial/by-id/usb-SimTech-if01-port0"
	reports := []providers.PortReport{
		{Device: "/dev/serial/by-id/usb-OBDLink-if00-port0", Role: providers.RoleELM},
		{Device: nmea, Role: providers.RoleNMEA},
	}
	if path := modemPath(reports, nmea); path != "" {
		t.Fatalf("a port the sweep called NMEA is not a modem, got %q", path)
	}

	reports[1].Role = providers.RoleModem
	if path := modemPath(reports, nmea); path != nmea {
		t.Fatalf("a port the sweep called a modem must be used as one, got %q", path)
	}

	// A path the sweep never saw is still probed; here it does not exist, so the
	// probe reports unknown rather than hanging or claiming a modem.
	if path := modemPath(reports, "/dev/does-not-exist"); path != "" {
		t.Fatalf("an unprobed missing device must not be taken for a modem, got %q", path)
	}
}
