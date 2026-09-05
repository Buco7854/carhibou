package main

import (
	"errors"
	"fmt"
	"maps"
	"net"
	"os"
	"path/filepath"
	"reflect"
	"slices"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Buco7854/carhibou/agent/internal/model"
	"github.com/Buco7854/carhibou/agent/internal/providers"
	agentruntime "github.com/Buco7854/carhibou/agent/internal/runtime"
	"github.com/Buco7854/carhibou/agent/internal/store"
	"github.com/Buco7854/carhibou/agent/internal/usbrecovery"
)

func TestLoopWatchdogDumpsStacksAndExits(t *testing.T) {
	var heartbeat atomic.Int64
	heartbeat.Store(time.Now().Add(-time.Minute - time.Second).UnixNano())
	written := make(chan string, 1)
	exited := make(chan int, 1)
	stop := make(chan struct{})
	defer close(stop)
	go runLoopWatchdog(
		&heartbeat, time.Millisecond,
		func() []byte { return []byte("all goroutine stacks") },
		func(content []byte) { written <- string(content) },
		func(code int) { exited <- code }, stop,
	)
	select {
	case content := <-written:
		if content != "all goroutine stacks" {
			t.Fatalf("dump=%q", content)
		}
	case <-time.After(time.Second):
		t.Fatal("watchdog did not dump stacks")
	}
	if code := <-exited; code != 1 {
		t.Fatalf("exit code=%d, want 1", code)
	}
}

func TestStartupSystemdNotifierSendsImmediately(t *testing.T) {
	stop := make(chan struct{})
	notified := make(chan struct{}, 1)
	go runSystemdNotifier(stop, time.Hour, func() { notified <- struct{}{} })
	select {
	case <-notified:
		close(stop)
	case <-time.After(time.Second):
		close(stop)
		t.Fatal("startup did not notify systemd immediately")
	}
}

func TestSystemdNotifierReusesOneConnectedSocket(t *testing.T) {
	path := filepath.Join(t.TempDir(), "notify.sock")
	listener, err := net.ListenUnixgram("unixgram", &net.UnixAddr{Name: path, Net: "unixgram"})
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	notifier, err := newSystemdNotifier(path)
	if err != nil {
		t.Fatal(err)
	}
	defer notifier.Close()
	connection := notifier.connection
	for range 2 {
		notifier.Notify()
		buffer := make([]byte, 32)
		if err := listener.SetReadDeadline(time.Now().Add(time.Second)); err != nil {
			t.Fatal(err)
		}
		count, _, err := listener.ReadFromUnix(buffer)
		if err != nil {
			t.Fatal(err)
		}
		if string(buffer[:count]) != "WATCHDOG=1" {
			t.Fatalf("notification=%q", buffer[:count])
		}
	}
	if notifier.connection != connection {
		t.Fatal("watchdog notifier replaced its connected socket")
	}
}

func TestSystemdWatchdogWarnsWhenNotifySocketIsMissing(t *testing.T) {
	if warning := systemdWatchdogWarning("90000000", "", nil); !strings.Contains(warning, "NOTIFY_SOCKET") {
		t.Fatalf("warning=%q", warning)
	}
	if warning := systemdWatchdogWarning("", "", nil); warning != "" {
		t.Fatalf("foreground run warning=%q", warning)
	}
}

func TestOBDUSBResetCooldownSurvivesProviderReplacement(t *testing.T) {
	now := time.Date(2026, 9, 4, 12, 0, 0, 0, time.UTC)
	resets := 0
	sharedResetter := cooledDownOBDResetter(func(string) error {
		resets++
		return nil
	}, func() time.Time { return now })
	firstProviderReset := sharedResetter
	secondProviderReset := sharedResetter
	if err := firstProviderReset("/dev/ttyUSB0"); err != nil {
		t.Fatal(err)
	}
	now = now.Add(time.Minute)
	// A skip has to say so. Returning success made a device that was never
	// touched read, in the failure that ends the session, as one a physical reset
	// had failed to revive.
	err := secondProviderReset("/dev/ttyUSB0")
	if !errors.Is(err, usbrecovery.ErrCoolingDown) {
		t.Fatalf("cooled-down reset returned %v, want the skip named", err)
	}
	if resets != 1 {
		t.Fatalf("physical resets=%d, want cooldown shared across provider replacement", resets)
	}
	now = now.Add(physicalRecoveryCooldown)
	if err := secondProviderReset("/dev/ttyUSB0"); err != nil {
		t.Fatal(err)
	}
	if resets != 2 {
		t.Fatalf("physical resets=%d, want reset after cooldown", resets)
	}
}

type cadencePosition struct{ fix *model.PositionFix }

func (position *cadencePosition) Read() (*model.PositionFix, error) { return position.fix, nil }

type burstTransitionVehicle struct {
	event string
}

func (vehicle *burstTransitionVehicle) ReadObservations() (model.MetricObservations, error) {
	vehicle.event = "charging.active changed to true"
	return model.MetricObservations{}, nil
}
func (vehicle *burstTransitionVehicle) TakeEvent() string {
	event := vehicle.event
	vehicle.event = ""
	return event
}
func (vehicle *burstTransitionVehicle) Close() {}

type countingUploadClient struct {
	uploads int
}

func (client *countingUploadClient) Upload(_ string, samples []model.Sample) ([]string, error) {
	client.uploads++
	acknowledged := make([]string, 0, len(samples))
	for _, sample := range samples {
		acknowledged = append(acknowledged, sample.ID)
	}
	return acknowledged, nil
}

func TestTransitionRaisedInsideBurstProducesOneSampleAndOneUpload(t *testing.T) {
	queue, err := store.OpenQueue(filepath.Join(t.TempDir(), "queue.sqlite3"))
	if err != nil {
		t.Fatal(err)
	}
	defer queue.Close()
	transport := &countingUploadClient{}
	agent := &agentruntime.Agent{
		Queue: queue, Client: transport, Position: agentruntime.EmptyPosition{},
		Vehicle: &burstTransitionVehicle{}, BootID: model.NewUUID(),
	}
	configuration := store.Configuration{
		Sampling: store.Interval{DefaultSeconds: 15, ParkedSeconds: 600},
		Upload:   store.Interval{DefaultSeconds: 30, ParkedSeconds: 600},
	}
	now := time.Now()
	_, nextUpload, err := collectAtCadence(agent, configuration, now, now.Add(10*time.Minute))
	if err != nil {
		t.Fatal(err)
	}
	if !nextUpload.Equal(now) {
		t.Fatalf("next upload=%s, want transition sample flushed at %s", nextUpload, now)
	}
	if _, err := agent.Upload(nil); err != nil {
		t.Fatal(err)
	}
	if transport.uploads != 1 {
		t.Fatalf("uploads=%d, want one", transport.uploads)
	}
	if reason := agent.PendingEvent(); reason != "" {
		t.Fatalf("transition survived its sample: %q", reason)
	}
	if agent.Sequence != 1 {
		t.Fatalf("samples=%d, want one", agent.Sequence)
	}
}

func TestCollectAtCadenceClampsUploadWhenTheVehicleStartsMoving(t *testing.T) {
	configuration := store.Configuration{
		Sampling: store.Interval{DefaultSeconds: 5, ParkedSeconds: 60},
		Upload:   store.Interval{DefaultSeconds: 30, ParkedSeconds: 300},
	}
	if got := reportingInterval(configuration, false); got != 300 {
		t.Fatalf("parked reporting interval=%d, want 300", got)
	}
	if got := reportingInterval(configuration, true); got != 30 {
		t.Fatalf("driving reporting interval=%d, want 30", got)
	}

	queue, err := store.OpenQueue(filepath.Join(t.TempDir(), "queue.sqlite3"))
	if err != nil {
		t.Fatal(err)
	}
	defer queue.Close()
	position := &cadencePosition{}
	agent := &agentruntime.Agent{
		Queue: queue, Position: position, Vehicle: agentruntime.EmptyVehicle{}, BootID: model.NewUUID(),
	}
	now := time.Date(2026, 8, 29, 12, 0, 0, 0, time.UTC)
	parkedUpload := now.Add(5 * time.Minute)
	_, nextUpload, err := collectAtCadence(agent, configuration, now, parkedUpload)
	if err != nil {
		t.Fatal(err)
	}
	if !nextUpload.Equal(parkedUpload) {
		t.Fatalf("stable parked state changed upload deadline to %s", nextUpload)
	}

	speed := 25.0
	position.fix = &model.PositionFix{Latitude: 48.8, Longitude: 2.3, Speed: &speed}
	transitionAt := now.Add(5 * time.Second)
	nextSample, nextUpload, err := collectAtCadence(agent, configuration, transitionAt, parkedUpload)
	if err != nil {
		t.Fatal(err)
	}
	if want := transitionAt.Add(5 * time.Second); !nextSample.Equal(want) {
		t.Fatalf("next sample=%s, want %s", nextSample, want)
	}
	if want := transitionAt.Add(30 * time.Second); !nextUpload.Equal(want) {
		t.Fatalf("next upload=%s, want %s", nextUpload, want)
	}

	pending, err := queue.Pending(10)
	if err != nil {
		t.Fatal(err)
	}
	if len(pending) != 2 {
		t.Fatalf("queued samples=%d, want 2", len(pending))
	}
	if pending[0].ReportingInterval == nil || *pending[0].ReportingInterval != 300 {
		t.Fatalf("parked promise=%v, want 300", pending[0].ReportingInterval)
	}
	if pending[1].ReportingInterval == nil || *pending[1].ReportingInterval != 30 {
		t.Fatalf("driving promise=%v, want 30", pending[1].ReportingInterval)
	}
}

func TestCommandsRejectNonPositiveDurations(t *testing.T) {
	tests := [][]string{
		{"gps-info", "--seconds", "0"},
		{"obd-info", "--seconds", "0"},
		{"obd-selftest", "--seconds", "0"},
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

func testPositionRecovery(initial resolvedDevices) *positionRecovery {
	return &positionRecovery{
		hardware:        store.DefaultHardware(),
		devices:         initial,
		samplingSeconds: 1,
		resolve:         func(store.Hardware, paths, bool) resolvedDevices { return resolvedDevices{} },
		reprobe: func(store.Hardware, paths, resolvedDevices, *serialOwnership) resolvedDevices {
			return resolvedDevices{}
		},
		start: func(resolvedDevices, int) (agentruntime.PositionProvider, func(), error) {
			return agentruntime.EmptyPosition{}, func() {}, nil
		},
		restartGNSS:   func(resolvedDevices) error { return nil },
		restartModule: func(resolvedDevices) error { return nil },
		resetUSB: func(_, _ []string) (usbrecovery.Device, error) {
			return usbrecovery.Device{}, errors.New("unexpected USB reset")
		},
		candidates: func() []string { return nil },
		forget:     func() {},
		now:        time.Now,
		sleep:      func(time.Duration) {},
	}
}

// A source that was proven to stream and then went silent is recovered through
// its known control port before any whole-device reset is considered.
func TestPositionRecoveryRestartsOnlyGNSSFirst(t *testing.T) {
	devices := resolvedDevices{gps: "/dev/gps", modem: "/dev/control", gpsStreams: true}
	recovery := testPositionRecovery(devices)
	recovery.attempted = true
	restarts := 0
	recovery.restartGNSS = func(got resolvedDevices) error {
		restarts++
		if got.gps != devices.gps || got.modem != devices.modem || got.gpsStreams != devices.gpsStreams {
			t.Fatalf("devices=%+v, want %+v", got, devices)
		}
		return nil
	}
	recovery.restartModule = func(resolvedDevices) error {
		t.Fatal("whole modem restarted after receiver-only recovery succeeded")
		return nil
	}

	if _, err := recovery.acquire(); err != nil {
		t.Fatal(err)
	}
	if restarts != 1 {
		t.Fatalf("receiver restarts=%d, want 1", restarts)
	}
}

func TestPositionRecoveryEscalatesFromATToOneVettedUSBReset(t *testing.T) {
	devices := resolvedDevices{gps: "/dev/gps", modem: "/dev/control", gpsStreams: true}
	recovery := testPositionRecovery(devices)
	recovery.attempted = true
	recovery.restartGNSS = func(resolvedDevices) error { return errors.New("receiver command timed out") }
	recovery.restartModule = func(resolvedDevices) error { return errors.New("modem command timed out") }
	recovery.candidates = func() []string { return []string{"/dev/control", "/dev/other"} }
	resetCalls := 0
	recovery.resetUSB = func(_, candidates []string) (usbrecovery.Device, error) {
		resetCalls++
		want := []string{"/dev/gps", "/dev/control", "/dev/other"}
		if strings.Join(candidates, ",") != strings.Join(want, ",") {
			t.Fatalf("candidates=%v, want %v", candidates, want)
		}
		return usbrecovery.Device{ProductID: "9001", BusNumber: 1, DeviceNumber: 3}, nil
	}
	refreshed := resolvedDevices{gps: "/dev/gps-new", modem: "/dev/control-new", gpsStreams: true}
	recovery.reprobe = func(store.Hardware, paths, resolvedDevices, *serialOwnership) resolvedDevices { return refreshed }
	forgot := 0
	recovery.forget = func() { forgot++ }

	if _, err := recovery.acquire(); err != nil {
		t.Fatal(err)
	}
	if resetCalls != 1 || forgot != 1 {
		t.Fatalf("USB resets=%d cache forgets=%d, want one of each", resetCalls, forgot)
	}
	if recovery.devices.gps != refreshed.gps || recovery.devices.modem != refreshed.modem {
		t.Fatalf("devices=%+v, want rediscovered %+v", recovery.devices, refreshed)
	}

	// Even if acquisition is asked again immediately, the physical reset has a
	// cooldown. This prevents an unplugged or genuinely failed modem reset loop.
	recovery.restartGNSS = func(resolvedDevices) error { return errors.New("still unavailable") }
	recovery.restartModule = func(resolvedDevices) error { return errors.New("still unavailable") }
	if _, err := recovery.acquire(); err != nil {
		t.Fatal(err)
	}
	if resetCalls != 1 {
		t.Fatalf("USB resets=%d, want cooldown to retain 1", resetCalls)
	}
}

func TestMissingPositionGetsASecondSweepBeforeUSBRecovery(t *testing.T) {
	recovery := testPositionRecovery(resolvedDevices{})
	freshSweeps := 0
	recovery.reprobe = func(store.Hardware, paths, resolvedDevices, *serialOwnership) resolvedDevices {
		freshSweeps++
		return resolvedDevices{}
	}
	resetCalls := 0
	recovery.resetUSB = func(_, _ []string) (usbrecovery.Device, error) {
		resetCalls++
		return usbrecovery.Device{}, usbrecovery.ErrNotFound
	}

	if _, err := recovery.acquire(); err == nil {
		t.Fatal("first missing-device attempt unexpectedly succeeded")
	}
	if resetCalls != 0 {
		t.Fatal("an initially enumerating modem was reset before one normal retry")
	}
	if _, err := recovery.acquire(); err == nil {
		t.Fatal("second missing-device attempt unexpectedly succeeded")
	}
	if freshSweeps != 2 || resetCalls != 1 {
		t.Fatalf("fresh sweeps=%d USB resets=%d, want 2 and 1", freshSweeps, resetCalls)
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

// fakeUSBSysfs builds the part of /sys a tty-to-USB-device walk reads.
type fakeUSBSysfs struct {
	root        string
	sysClassTTY string
	devRoot     string
	devices     map[string]string
}

func newFakeUSBSysfs(t *testing.T) *fakeUSBSysfs {
	t.Helper()
	root := t.TempDir()
	tree := &fakeUSBSysfs{
		root:        root,
		sysClassTTY: filepath.Join(root, "sys", "class", "tty"),
		devRoot:     filepath.Join(root, "dev"),
		devices:     map[string]string{},
	}
	for _, path := range []string{tree.sysClassTTY, tree.devRoot} {
		if err := os.MkdirAll(path, 0o755); err != nil {
			t.Fatal(err)
		}
	}
	return tree
}

func (tree *fakeUSBSysfs) addDevice(t *testing.T, name string, attributes map[string]string) {
	t.Helper()
	directory := filepath.Join(tree.root, "sys", "devices", name)
	if err := os.MkdirAll(directory, 0o755); err != nil {
		t.Fatal(err)
	}
	for attribute, value := range attributes {
		if err := os.WriteFile(filepath.Join(directory, attribute), []byte(value+"\n"), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	tree.devices[name] = directory
}

func (tree *fakeUSBSysfs) addTTY(t *testing.T, name, device string) string {
	t.Helper()
	interfacePath := filepath.Join(tree.devices[device], device+":1.0", "tty", name)
	if err := os.MkdirAll(interfacePath, 0o755); err != nil {
		t.Fatal(err)
	}
	classPath := filepath.Join(tree.sysClassTTY, name)
	if err := os.MkdirAll(classPath, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(interfacePath, filepath.Join(classPath, "device")); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(tree.devRoot, name)
	if err := os.WriteFile(path, nil, 0o644); err != nil {
		t.Fatal(err)
	}
	return path
}

func (tree *fakeUSBSysfs) install(t *testing.T) *[][]usbrecovery.DeviceID {
	t.Helper()
	previousResolver, previousInstall := newUSBResolver, installUSBRecoveryRule
	granted := &[][]usbrecovery.DeviceID{}
	newUSBResolver = func() *usbrecovery.Recovery {
		return usbrecovery.New(usbrecovery.Config{
			SysClassTTYRoot: tree.sysClassTTY,
			USBBusRoot:      filepath.Join(tree.devRoot, "bus", "usb"),
		})
	}
	installUSBRecoveryRule = func(devices []usbrecovery.DeviceID) error {
		*granted = append(*granted, devices)
		return nil
	}
	t.Cleanup(func() { newUSBResolver, installUSBRecoveryRule = previousResolver, previousInstall })
	return granted
}

// Reset rights follow the devices the configured ttys belong to, whatever they
// are, and a modem publishing several interfaces is granted once rather than
// once per interface.
func TestUSBRecoveryRightsFollowTheConfiguredDevices(t *testing.T) {
	tree := newFakeUSBSysfs(t)
	tree.addDevice(t, "1-1", map[string]string{
		"idVendor": "1e0e", "idProduct": "9001", "busnum": "1", "devnum": "4",
		"serial": "0123456789", "manufacturer": "SimTech, Incorporated",
	})
	tree.addDevice(t, "1-2", map[string]string{
		"idVendor": "0403", "idProduct": "6015", "busnum": "1", "devnum": "5",
		"manufacturer": "ScanTool.net LLC",
	})
	gps := tree.addTTY(t, "ttyUSB1", "1-1")
	modem := tree.addTTY(t, "ttyUSB2", "1-1")
	obd := tree.addTTY(t, "ttyUSB0", "1-2")
	granted := tree.install(t)

	grantUSBRecoveryRights([]string{gps, obd, modem})
	if len(*granted) != 1 {
		t.Fatalf("granted %d rules, want one", len(*granted))
	}
	want := []usbrecovery.DeviceID{
		{VendorID: "1e0e", ProductID: "9001", Serial: "0123456789"},
		{VendorID: "0403", ProductID: "6015"},
	}
	if !reflect.DeepEqual((*granted)[0], want) {
		t.Fatalf("granted %+v, want %+v", (*granted)[0], want)
	}
}

// With nothing to grant, no rule is written — an empty one would revoke the
// rights a working installation already has — and the diagnosis names the
// devices that are actually attached rather than the ones expected.
func TestUSBRecoveryRightsReportWhatWasFoundWhenNothingMatches(t *testing.T) {
	tree := newFakeUSBSysfs(t)
	tree.addDevice(t, "1-1", map[string]string{
		"idVendor": "0403", "idProduct": "6001", "busnum": "1", "devnum": "3",
		"manufacturer": "FTDI", "product": "FT232R USB UART",
	})
	present := tree.addTTY(t, "ttyUSB0", "1-1")
	granted := tree.install(t)

	grantUSBRecoveryRights([]string{filepath.Join(tree.devRoot, "ttyUSB9")})
	if len(*granted) != 0 {
		t.Fatalf("granted a rule with nothing resolved: %+v", *granted)
	}
	devices, descriptions := usbRecoveryTargets([]string{present})
	if len(devices) != 1 || len(descriptions) != 1 {
		t.Fatalf("devices=%+v descriptions=%v", devices, descriptions)
	}
	for _, descriptor := range []string{present, "0403:6001", `"FTDI"`, `"FT232R USB UART"`} {
		if !strings.Contains(descriptions[0], descriptor) {
			t.Fatalf("description %q is missing %s", descriptions[0], descriptor)
		}
	}
}

// fakeSerialSet is a set of serial ports that can be held exclusively, the way
// a real one is: opening a port another owner has is an error, not a wait.
type fakeSerialSet struct {
	mutex sync.Mutex
	roles map[string]providers.SerialRole
	held  map[string]string
	opens map[string]int
	// busy records every attempt to open a port another owner had. It is the
	// evidence the whole exercise is about: on the car it appeared as probe lines
	// reporting "Serial port busy" and as acquisitions that failed for no reason
	// of their own.
	busy []string
}

func newFakeSerialSet(roles map[string]providers.SerialRole) *fakeSerialSet {
	return &fakeSerialSet{roles: roles, held: map[string]string{}, opens: map[string]int{}}
}

func (set *fakeSerialSet) paths() []string {
	set.mutex.Lock()
	defer set.mutex.Unlock()
	return slices.Sorted(maps.Keys(set.roles))
}

// open takes the port for owner, or reports it busy the way the driver does.
func (set *fakeSerialSet) open(owner, device string) error {
	set.mutex.Lock()
	defer set.mutex.Unlock()
	set.opens[device]++
	if holder, held := set.held[device]; held && holder != owner {
		collision := fmt.Sprintf("%s opened %s while %s held it: Serial port busy", owner, device, holder)
		set.busy = append(set.busy, collision)
		return errors.New(collision)
	}
	set.held[device] = owner
	return nil
}

// quiesce waits until nothing is opening ports any more. Closing a retrying
// owner deliberately does not wait for an acquisition already in flight, so
// without this a leftover sweep from one case walks into the next one's fake set.
func (set *fakeSerialSet) quiesce(t *testing.T) {
	t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	settled := 0
	for time.Now().Before(deadline) {
		set.mutex.Lock()
		total := 0
		for _, count := range set.opens {
			total += count
		}
		set.mutex.Unlock()
		time.Sleep(4 * probeHold)
		set.mutex.Lock()
		after := 0
		for _, count := range set.opens {
			after += count
		}
		set.mutex.Unlock()
		if total == after {
			settled++
			if settled == 2 {
				return
			}
			continue
		}
		settled = 0
	}
	t.Fatal("serial probing never stopped after both owners were closed")
}

func (set *fakeSerialSet) collisions() []string {
	set.mutex.Lock()
	defer set.mutex.Unlock()
	return append([]string(nil), set.busy...)
}

func (set *fakeSerialSet) release(owner string) {
	set.mutex.Lock()
	defer set.mutex.Unlock()
	for device, holder := range set.held {
		if holder == owner {
			delete(set.held, device)
		}
	}
}

// probe opens the port and holds it while it classifies, which is what a real
// probe does for several seconds and what makes a sweep collide with the other
// source rather than merely race it.
func (set *fakeSerialSet) probe(device string) providers.PortReport {
	if err := set.open("probe", device); err != nil {
		return providers.PortReport{Device: device, Role: providers.RoleUnknown, Error: err.Error()}
	}
	time.Sleep(probeHold)
	defer set.release("probe")
	set.mutex.Lock()
	defer set.mutex.Unlock()
	report := providers.PortReport{Device: device, Role: set.roles[device]}
	switch report.Role {
	case providers.RoleNMEA:
		report.NMEA = true
	case providers.RoleELM:
		report.ELM = true
	case providers.RoleModem:
		report.Modem = true
	}
	return report
}

// install replaces the three host discovery operations plus the vehicle
// provider constructor, which is everything an acquirer touches.
func (set *fakeSerialSet) install(t *testing.T) {
	t.Helper()
	previousCandidates, previousSweep := serialCandidates, sweepPorts
	previousKnown, previousBuild := probeKnownPort, buildVehicleProvider
	serialCandidates = set.paths
	sweepPorts = func(devices []string, onReport func(providers.PortReport)) []providers.PortReport {
		reports := make([]providers.PortReport, 0, len(devices))
		for _, device := range devices {
			report := set.probe(device)
			if onReport != nil {
				onReport(report)
			}
			reports = append(reports, report)
		}
		return reports
	}
	probeKnownPort = set.probe
	buildVehicleProvider = func(
		device string, _ store.Configuration, _ func(string) error,
	) (agentruntime.VehicleProvider, error) {
		return &fakeOwnedVehicle{set: set, device: device}, nil
	}
	t.Cleanup(func() {
		serialCandidates, sweepPorts = previousCandidates, previousSweep
		probeKnownPort, buildVehicleProvider = previousKnown, previousBuild
	})
}

type fakeOwnedVehicle struct {
	set     *fakeSerialSet
	device  string
	failure string
}

func (vehicle *fakeOwnedVehicle) Start() {
	if err := vehicle.set.open(vehicleRole, vehicle.device); err != nil {
		vehicle.failure = "open " + vehicle.device + ": " + err.Error()
	}
}
func (vehicle *fakeOwnedVehicle) Status() string   { return vehicle.failure }
func (vehicle *fakeOwnedVehicle) Describe() string { return "fake vehicle on " + vehicle.device }
func (vehicle *fakeOwnedVehicle) Close()           { vehicle.set.release(vehicleRole) }
func (vehicle *fakeOwnedVehicle) ReadObservations() (model.MetricObservations, error) {
	return model.MetricObservations{}, nil
}

type fakeOwnedPosition struct{ device string }

func (position *fakeOwnedPosition) Read() (*model.PositionFix, error) { return nil, nil }
func (position *fakeOwnedPosition) Describe() string                  { return "fake position on " + position.device }

// Both sources reacquire on their own goroutines, and every retry used to sweep
// every port: the vehicle sweep skipped only the GPS path resolved at startup
// and the position sweep skipped the OBD path only once one had been detected,
// so each could open the port the other was using and fail it as busy. Neither
// may now touch a port the other has declared.
func TestBothAcquirersAvoidThePortsTheOtherHolds(t *testing.T) {
	// Both directions of the collision, repeated, because either goroutine may
	// reach its port first: the position sweep landing on the adapter the vehicle
	// source is opening, and the vehicle sweep landing on the receiver the
	// position source is holding.
	for attempt := 0; attempt < 5; attempt++ {
		set := newFakeSerialSet(map[string]providers.SerialRole{
			"/dev/ttyUSB0": providers.RoleELM,
			"/dev/ttyUSB1": providers.RoleNMEA,
			"/dev/ttyUSB2": providers.RoleModem,
		})
		set.install(t)
		locations := paths{config: t.TempDir(), data: t.TempDir()}
		hardware := store.Hardware{GPS: store.Auto, OBD: store.Auto}
		ownership := newSerialOwnership()

		// Nothing is detected yet, which is the state in which the name-based
		// exclusions were empty and the two sweeps walked over each other.
		position := agentruntime.NewRetryingPositionProvider(func() (agentruntime.PositionProvider, error) {
			devices := resolvePositionDevices(hardware, locations, resolvedDevices{}, ownership)
			if devices.gps == "" {
				return nil, fmt.Errorf("no GPS device found")
			}
			ownership.claim(positionRole, devices.gps, devices.modem)
			return &fakeOwnedPosition{device: devices.gps}, nil
		})
		vehicle := agentruntime.NewRetryingVehicleProvider(serviceVehicleAcquirer(
			hardware, locations, "", "/dev/ttyUSB0", "",
			func() store.Configuration { return store.Configuration{} },
			ownership,
		))
		announced := recordedTransitions(t, position, vehicle)
		position.Start()
		vehicle.Start()

		// Both readiness lines, because an empty status means "healthy" and "never
		// acquired anything" alike.
		ready := func() bool {
			lines := announced()
			for _, prefix := range []string{"vehicle source ready", "position source ready"} {
				if !slices.ContainsFunc(lines, func(line string) bool { return strings.HasPrefix(line, prefix) }) {
					return false
				}
			}
			return true
		}
		deadline := time.Now().Add(10 * time.Second)
		for time.Now().Before(deadline) && !ready() {
			time.Sleep(5 * time.Millisecond)
		}
		if status := vehicle.Status(); status != "" {
			t.Fatalf("attempt %d: vehicle source never acquired: %s", attempt, status)
		}
		if status := position.Status(); status != "" {
			t.Fatalf("attempt %d: position source never acquired: %s", attempt, status)
		}
		if !ready() {
			t.Fatalf("attempt %d: both sources never became ready: %v", attempt, announced())
		}
		for _, line := range append(announced(), set.collisions()...) {
			if strings.Contains(line, "busy") {
				t.Fatalf("attempt %d: an acquirer touched a port the other held: %s", attempt, line)
			}
		}
		vehicle.Close()
		position.Close()
		set.quiesce(t)
	}
}

// probeHold is how long the fake probe keeps a port, standing in for the seconds
// a real one spends listening and writing.
const probeHold = 25 * time.Millisecond

// The vehicle sweep excluded the GPS path the service resolved when it started,
// which is not the path the position source is on after it has recovered onto
// another interface. It now asks what that source actually holds.
func TestVehicleSweepSkipsThePortThePositionSourceMovedTo(t *testing.T) {
	set := newFakeSerialSet(map[string]providers.SerialRole{
		"/dev/ttyUSB0": providers.RoleELM,
		"/dev/ttyUSB1": providers.RoleNMEA,
		"/dev/ttyUSB2": providers.RoleModem,
	})
	set.install(t)
	locations := paths{config: t.TempDir(), data: t.TempDir()}
	ownership := newSerialOwnership()
	// The receiver moved to USB2 after a module reset; USB1 is the stale name the
	// vehicle acquirer captured at startup.
	ownership.claim(positionRole, "/dev/ttyUSB2")
	if err := set.open(positionRole, "/dev/ttyUSB2"); err != nil {
		t.Fatal(err)
	}

	device, err := reprobeVehicleDevice(locations, "/dev/ttyUSB1", ownership)
	if err != nil {
		t.Fatal(err)
	}
	if device != "/dev/ttyUSB0" {
		t.Fatalf("resolved OBD device %q, want the adapter", device)
	}
	if collisions := set.collisions(); len(collisions) != 0 {
		t.Fatalf("the vehicle sweep opened a port the position source held: %v", collisions)
	}
}

// A retry that already knows its adapter asks that port alone. Sweeping every
// port to rediscover hardware that never moved is seconds of opening and writing
// to devices the other source may be using, on every backoff.
func TestVehicleRetryAsksTheKnownAdapterBeforeSweeping(t *testing.T) {
	set := newFakeSerialSet(map[string]providers.SerialRole{
		"/dev/ttyUSB0": providers.RoleELM,
		"/dev/ttyUSB1": providers.RoleNMEA,
		"/dev/ttyUSB2": providers.RoleModem,
	})
	set.install(t)
	locations := paths{config: t.TempDir(), data: t.TempDir()}
	if err := detectionStore(locations).Save(store.Detection{OBD: "/dev/ttyUSB0"}); err != nil {
		t.Fatal(err)
	}
	previousExists := fileExistsFunc
	fileExistsFunc = func(string) bool { return true }
	t.Cleanup(func() { fileExistsFunc = previousExists })

	device, err := reprobeVehicleDevice(locations, "", newSerialOwnership())
	if err != nil {
		t.Fatal(err)
	}
	if device != "/dev/ttyUSB0" {
		t.Fatalf("resolved OBD device %q", device)
	}
	set.mutex.Lock()
	defer set.mutex.Unlock()
	for _, port := range []string{"/dev/ttyUSB1", "/dev/ttyUSB2"} {
		if set.opens[port] != 0 {
			t.Fatalf("the known adapter answered, yet %s was opened %d times", port, set.opens[port])
		}
	}
}

// recordedTransitions collects every transition both owners announce, which is
// also the coverage that the journal now gets one line per distinct status.
func recordedTransitions(t *testing.T, position *agentruntime.RetryingPositionProvider, vehicle *agentruntime.RetryingVehicleProvider) func() []string {
	t.Helper()
	var mutex sync.Mutex
	lines := []string{}
	record := func(line string) {
		mutex.Lock()
		defer mutex.Unlock()
		lines = append(lines, line)
		t.Log(line)
	}
	position.SetReporter(record)
	vehicle.SetReporter(record)
	return func() []string {
		mutex.Lock()
		defer mutex.Unlock()
		return append([]string(nil), lines...)
	}
}
