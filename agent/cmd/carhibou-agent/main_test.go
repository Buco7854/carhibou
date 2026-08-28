package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/Buco7854/carhibou/agent/internal/providers"
)

func TestCommandsRejectNonPositiveDurations(t *testing.T) {
	tests := [][]string{
		{"gps-info", "--seconds", "0"},
		{"obd-info", "--seconds", "0"},
		{"can-record", "--seconds", "-1", "capture.jsonl"},
		{"run", "--config-sync-seconds", "0"},
	}
	for _, arguments := range tests {
		if err := execute(arguments); err == nil || !strings.Contains(err.Error(), "greater than zero") {
			t.Fatalf("execute(%v) error = %v", arguments, err)
		}
	}
}

func TestOBDWatchCANIDAndCountsUseDisplayIdentifiers(t *testing.T) {
	for input, want := range map[string]int{"373": 0x373, "0x101": 0x101, "18DAF110": 0x18DAF110} {
		parsed, err := parseOptionalCANID(input)
		if err != nil || parsed == nil || *parsed != want {
			t.Fatalf("parseOptionalCANID(%q)=%v, %v; want %#x", input, parsed, err, want)
		}
	}
	if _, err := parseOptionalCANID("not-hex"); err == nil {
		t.Fatal("invalid watch identifier accepted")
	}
	counts := canIDCounts(map[int]int{0x101: 12, 0x18DAF110: 3})
	if counts["101"] != 12 || counts["18DAF110"] != 3 {
		t.Fatalf("counts=%v", counts)
	}
}

func TestFlaggedCANFramesAppearInTheOBDCensus(t *testing.T) {
	seen := map[int]int{}
	for _, line := range []string{
		"374 8F 90 9D FE 4F 4B 47 14 <DATA ERROR",
		"373 BB BB 7F 4E 0C 65 00 16 <DATA ERROR",
		"412 FE 00 01 19 7A 00 21 12 <DATA ERROR",
		"298 43 42 4A 42 43 00 27 10 <DATA ERROR",
	} {
		frame, err := providers.ParseCANFrame(line, 1)
		if err != nil {
			t.Fatal(err)
		}
		seen[frame.CANID]++
	}
	ids := strings.Join(sortedCANIDs(seen), ",")
	if ids != "298,373,374,412" {
		t.Fatalf("can_ids=%s", ids)
	}
}

// "config" without --pull must never need credentials or the network, because it
// is the first thing an operator runs on an agent that cannot reach the server.
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
		{Device: "/dev/serial/by-id/usb-OBDLink-if00-port0", ELM: true},
		{Device: nmea, NMEA: true},
	}
	if path := modemPath(reports, nmea); path != "" {
		t.Fatalf("a port that only streams is not a control port, got %q", path)
	}

	// The same interface commonly does both, which is the whole reason the sweep
	// records capabilities rather than one role.
	reports[1].Modem = true
	if path := modemPath(reports, nmea); path != nmea {
		t.Fatalf("a streaming port that also accepts AT must be used as one, got %q", path)
	}

	// A path the sweep never saw is still probed; here it does not exist, so the
	// probe reports unknown rather than hanging or claiming a modem.
	if path := modemPath(reports, "/dev/does-not-exist"); path != "" {
		t.Fatalf("an unprobed missing device must not be taken for a modem, got %q", path)
	}
}

// A receiver that is already publishing sentences needs nothing switched on, and
// the control port must be left shut. Opening it anyway asked a module that was
// plainly working whether it was, and printed a failure to enable something
// already enabled, on an interface that answers only intermittently.
func TestStreamingGPSNeverOpensTheControlPort(t *testing.T) {
	devices := resolvedDevices{
		gps:        "/dev/carhibou-absent-gps",
		modem:      "/dev/carhibou-absent-modem",
		gpsStreams: true,
	}
	position, closePosition, err := startPosition(devices, 1)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	defer closePosition()
	// Both paths are absent, so anything that opened one would have failed. The
	// stream provider opens lazily, which is what lets this assert the choice
	// rather than the hardware.
	if _, ok := position.(*providers.NMEAProvider); !ok {
		t.Fatalf("position source is %T, want the sentence stream", position)
	}
}

// With nothing streaming, the control port is both what switches the receiver on
// and the only thing left able to answer a position.
func TestPositionFallsBackToTheControlPortWhenNothingStreams(t *testing.T) {
	devices := resolvedDevices{gps: "/dev/carhibou-absent", modem: "/dev/carhibou-absent"}
	position, closePosition, err := startPosition(devices, 1)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	defer closePosition()
	if _, ok := position.(*providers.ModemPort); !ok {
		t.Fatalf("position source is %T, want the control port", position)
	}
}

// A hardware command must refuse while the service holds the ports, rather than
// warn. Root is exempt from the exclusive-access flag, so both processes open the
// port and split one stream: across two runs seconds apart the same adapter
// identified itself and then timed out, which is arbitrary rather than degraded.
func TestHardwareCommandsRefuseWhileTheServiceHoldsThePorts(t *testing.T) {
	previous := forceHardware
	t.Cleanup(func() { forceHardware = previous })

	// The service is not running under test, so the check has to pass on its own.
	forceHardware = false
	if err := requireExclusiveHardware(); err != nil {
		t.Fatalf("with no service running the command must proceed: %v", err)
	}

	// --force is the escape hatch, and must work even were the service up.
	forceHardware = true
	if err := requireExclusiveHardware(); err != nil {
		t.Fatalf("--force must let the command run: %v", err)
	}
}

func TestForceIsAcceptedBeforeTheCommand(t *testing.T) {
	previous := forceHardware
	t.Cleanup(func() { forceHardware = previous })
	forceHardware = false

	locations, remaining, err := globalArguments([]string{"--force", "--data-dir", "/tmp/x", "gps-info"})
	if err != nil {
		t.Fatal(err)
	}
	if !forceHardware {
		t.Fatal("--force was not taken")
	}
	if locations.data != "/tmp/x" || len(remaining) != 1 || remaining[0] != "gps-info" {
		t.Fatalf("data=%q remaining=%v", locations.data, remaining)
	}
}
