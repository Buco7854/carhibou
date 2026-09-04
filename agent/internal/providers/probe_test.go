package providers

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
	"time"

	"go.bug.st/serial"
)

// scriptedPort answers like a serial device: it streams whatever it was primed
// with, and replies to a written command from a lookup table.
type scriptedPort struct {
	stream  string
	replies map[string]string
	pending string
}

func (port *scriptedPort) Read(buffer []byte) (int, error) {
	if port.pending == "" {
		port.pending = port.stream
		port.stream = ""
	}
	if port.pending == "" {
		time.Sleep(5 * time.Millisecond)
		return 0, nil
	}
	count := copy(buffer, port.pending)
	port.pending = port.pending[count:]
	return count, nil
}

func (port *scriptedPort) Write(payload []byte) (int, error) {
	command := string(payload)
	for prefix, reply := range port.replies {
		if len(command) >= len(prefix) && command[:len(prefix)] == prefix {
			port.pending = reply
			return len(payload), nil
		}
	}
	return len(payload), nil
}

func (port *scriptedPort) ResetInputBuffer() error            { port.pending = ""; return nil }
func (port *scriptedPort) Close() error                       { return nil }
func (port *scriptedPort) ResetOutputBuffer() error           { return nil }
func (port *scriptedPort) SetDTR(bool) error                  { return nil }
func (port *scriptedPort) SetRTS(bool) error                  { return nil }
func (port *scriptedPort) SetReadTimeout(time.Duration) error { return nil }
func (port *scriptedPort) SetMode(*serial.Mode) error         { return nil }
func (port *scriptedPort) GetModemStatusBits() (*serial.ModemStatusBits, error) {
	return &serial.ModemStatusBits{}, nil
}
func (port *scriptedPort) Drain() error              { return nil }
func (port *scriptedPort) Break(time.Duration) error { return nil }

var fastProbe = probeConversation{
	listen:        60 * time.Millisecond,
	identity:      60 * time.Millisecond,
	modemCommand:  60 * time.Millisecond,
	modemAttempts: defaultConversation.modemAttempts,
}

func TestClassifyIdentifiesAnNMEAStreamWithoutWriting(t *testing.T) {
	port := &scriptedPort{stream: nmeaSentence("GPGGA,120000.00,4851.0000,N,00220.0000,E,1,08,1.0,89.6,M,,,,") + "\r\n"}
	report := ClassifyPort(port, fastProbe)
	if !report.NMEA || report.Role != RoleNMEA {
		t.Fatalf("%+v, want nmea", report)
	}
}

// A port that streams sentences has identified itself, and is left alone.
//
// It used to be asked for AT as well, on the reasoning that the streaming
// interface is often the one that switches the stream on. The cost of that was
// paid on a SIM7600: AT traffic aimed at an NMEA interface is the thing most
// likely to wedge the module, and since sweeps repeat on a reacquisition backoff
// rather than running once at startup, it repeats for as long as anything is
// missing. SelectRoles finds the control interface among the ports that did not
// stream, which is where it lives on every module this has been seen on.
func TestClassifyNeverWritesToAPortThatStreamsNMEA(t *testing.T) {
	port := &recordingProbePort{scriptedPort: scriptedPort{
		stream:  nmeaSentence("GPGGA,120000.00,4851.0000,N,00220.0000,E,1,08,1.0,89.6,M,,,,") + "\r\n",
		replies: map[string]string{"AT\r": "AT\r\r\nOK\r\n", "ATI": "ATI\r\rSIM7600\r\r>"},
	}}
	report := ClassifyPort(port, fastProbe)
	if !report.NMEA || report.Role != RoleNMEA {
		t.Fatalf("%+v, want the stream to classify the port", report)
	}
	if report.Modem || report.ELM {
		t.Fatalf("%+v, want no answer that could only come from a command", report)
	}
	if port.written != "" {
		t.Fatalf("wrote %q to a port that was already answering by itself", port.written)
	}
}

// A port that says nothing on its own is still asked, because silence identifies
// nothing and the adapter and the control interface both have to be found.
func TestClassifyStillQuestionsASilentPort(t *testing.T) {
	port := &recordingProbePort{scriptedPort: scriptedPort{
		replies: map[string]string{"AT\r": "AT\r\r\nOK\r\n"},
	}}
	report := ClassifyPort(port, fastProbe)
	if !report.Modem || report.Role != RoleModem {
		t.Fatalf("%+v, want the silent port identified as a modem", report)
	}
	if !strings.Contains(port.written, "ATI") || !strings.Contains(port.written, "AT\r") {
		t.Fatalf("wrote %q, want both questions asked of a silent port", port.written)
	}
}

// recordingProbePort keeps what was written so a test can assert that nothing was.
type recordingProbePort struct {
	scriptedPort
	written string
}

func (port *recordingProbePort) Write(payload []byte) (int, error) {
	port.written += string(payload)
	return port.scriptedPort.Write(payload)
}

// An ELM adapter answers plain AT as well, so the enquiry has to stop once it has
// identified itself or every OBD adapter would be filed as a modem.
func TestClassifyDoesNotMistakeAnELMAdapterForAModem(t *testing.T) {
	port := &scriptedPort{replies: map[string]string{
		"ATI":  "ATI\r\rELM327 v1.3a\r\r>",
		"AT\r": "AT\r\r\nOK\r\n",
	}}
	report := ClassifyPort(port, fastProbe)
	if !report.ELM || report.Modem {
		t.Fatalf("%+v, want an adapter that is not also a modem", report)
	}
}

func TestClassifyIdentifiesAnELMAdapter(t *testing.T) {
	port := &scriptedPort{replies: map[string]string{"ATI": "ATI\r\rELM327 v1.3a\r\r>"}}
	report := ClassifyPort(port, fastProbe)
	if report.Role != RoleELM || report.Identity != "ELM327 v1.3a" {
		t.Fatalf("%+v, want an ELM adapter", report)
	}
}

func TestClassifyIdentifiesAModemControlPort(t *testing.T) {
	port := &scriptedPort{replies: map[string]string{"AT\r": "AT\r\r\nOK\r\n"}}
	if report := ClassifyPort(port, fastProbe); !report.Modem || report.Role != RoleModem {
		t.Fatalf("%+v, want modem", report)
	}
}

// A SIM7600 identifies itself when asked ATI before answering the plain AT used
// for classification. Its completed, non-ELM identity reply must move the probe
// straight on instead of making a healthy modem consume the whole first window.
func TestClassifyDoesNotWaitOutTheIdentityWindowForAHealthyModem(t *testing.T) {
	timing := probeConversation{
		listen:       time.Millisecond,
		identity:     500 * time.Millisecond,
		modemCommand: 500 * time.Millisecond,
	}
	port := &scriptedPort{replies: map[string]string{
		"ATI":  "ATI\r\r\nSIMCOM_SIM7600\r\n\r\nOK\r\n",
		"AT\r": "AT\r\r\nOK\r\n",
	}}
	started := time.Now()
	report := ClassifyPort(port, timing)
	if !report.Modem || report.Role != RoleModem {
		t.Fatalf("%+v, want modem", report)
	}
	if elapsed := time.Since(started); elapsed >= timing.identity {
		t.Fatalf("healthy modem took %s; completed ATI reply should avoid the %s identity wait", elapsed, timing.identity)
	}
}

// wakingPort answers like a SIM7600 control interface: it discards the first few
// commands sent after its port is opened, then answers normally.
type wakingPort struct {
	scriptedPort
	swallow int
	seen    int
}

func (port *wakingPort) Write(payload []byte) (int, error) {
	port.seen++
	if port.seen <= port.swallow {
		// Accepted by the driver, never acted on by the module.
		return len(payload), nil
	}
	return port.scriptedPort.Write(payload)
}

// A SIM7600 control interface routinely ignores the first command sent after its
// port is opened. Asking once recorded that wake-up loss as "not a modem", and
// since that interface is the only one able to switch the receiver back on, the
// module was left with no route to recovery: the reported symptom was a GPS that
// returned only after the Raspberry Pi was physically unplugged, on hardware whose
// control port answered a terminal immediately. The agent's own modem client
// already wakes a port this way before every state change; the sweep that has to
// find that port must be no less patient.
func TestClassifyWakesAControlPortThatIgnoresItsFirstCommands(t *testing.T) {
	for _, swallowed := range []int{1, 2} {
		port := &wakingPort{
			scriptedPort: scriptedPort{replies: map[string]string{"AT\r": "AT\r\r\nOK\r\n"}},
			swallow:      swallowed,
		}
		report := ClassifyPort(port, fastProbe)
		if !report.Modem || report.Role != RoleModem {
			t.Fatalf("swallowing %d commands gave %+v, want the control port still identified", swallowed, report)
		}
	}
}

// A port that has genuinely stopped answering must not be rescued by repetition,
// or every dead interface would cost the full modem window on every sweep.
func TestClassifyGivesUpOnAPortThatNeverWakes(t *testing.T) {
	port := &wakingPort{
		scriptedPort: scriptedPort{replies: map[string]string{"AT\r": "AT\r\r\nOK\r\n"}},
		swallow:      99,
	}
	if report := ClassifyPort(port, fastProbe); report.Role != RoleUnknown {
		t.Fatalf("%+v, want unknown", report)
	}
}

// budget() is the figure the watchdog is derived from, so it has to be the truth
// rather than a hopeful estimate.
//
// It was neither. Every phase set one fixed read timeout and only re-checked the
// clock between reads, so a silent port overran each of its three phases by up to
// a full read. The accumulated overrun pushed a probe past the watchdog guarding
// it — and the port needing all three phases before it answers is exactly the
// modem control interface, which was therefore the first to be abandoned.
func TestASilentPortCostsNoMoreThanTheDeclaredBudget(t *testing.T) {
	previous := openPort
	openPort = func(string) (serial.Port, error) { return &mutePort{}, nil }
	t.Cleanup(func() { openPort = previous })

	started := time.Now()
	report := probeDevice(openPort, "/dev/silent")
	elapsed := time.Since(started)

	if report.Role != RoleUnknown {
		t.Fatalf("%+v, want unknown", report)
	}
	// The tolerance covers scheduling, not structure. The defect being guarded
	// against overran by a whole read timeout per phase, an order of magnitude
	// above this.
	if budget := defaultConversation.budget(); elapsed > budget+50*time.Millisecond {
		t.Fatalf("a silent port cost %s, above the %s budget the watchdog is derived from", elapsed, budget)
	}
}

// mutePort is a port that is open and healthy but says nothing, and it consumes a
// read for exactly as long as it was told to wait. A real serial port behaves this
// way; a fake that returns early hides the phase overruns this file exists to catch.
type mutePort struct {
	scriptedPort
	timeout time.Duration
}

func (port *mutePort) SetReadTimeout(timeout time.Duration) error {
	port.timeout = timeout
	return nil
}

func (port *mutePort) Read([]byte) (int, error) {
	time.Sleep(port.timeout)
	return 0, nil
}

func TestClassifyLeavesASilentPortUnknown(t *testing.T) {
	if report := ClassifyPort(&scriptedPort{}, fastProbe); report.Role != RoleUnknown {
		t.Fatalf("%+v, want unknown", report)
	}
}

// The reported field failure, reproduced end to end at the level it went wrong.
//
// A SIM7600 whose receiver is powered down publishes no NMEA on any interface, so
// every one of its five ports has to be carried through the whole conversation
// before anything can be concluded. That is the moment the sweep used to give up:
// the watchdog fired, the control port was filed as unknown, and with no control
// port there was nothing left able to switch the receiver back on. The module
// stayed mute until the Raspberry Pi was physically unplugged, which is the only
// action that powers the receiver up again.
//
// What must hold is narrow and total: with the receiver off, the sweep still finds
// the control interface, and SelectRoles still yields a position source.
func TestASleepingModuleStillYieldsAControlPortAndAPositionSource(t *testing.T) {
	answersAT := func(swallow int) serial.Port {
		return &wakingPort{
			scriptedPort: scriptedPort{replies: map[string]string{
				"AT\r":  "AT\r\r\nOK\r\n",
				"ATI\r": "ATI\r\r\nSIMCOM_SIM7600E-H\r\n\r\nOK\r\n",
			}},
			swallow: swallow,
		}
	}
	ports := []struct {
		device string
		port   serial.Port
	}{
		// The diagnostic interface never answers a character stream.
		{"/dev/serial/by-id/usb-SimTech-if00-port0", &scriptedPort{}},
		// The receiver's own interface: silent, because GNSS is powered down.
		{"/dev/serial/by-id/usb-SimTech-if01-port0", &scriptedPort{}},
		// The control interface, ignoring the commands that wake it, as this
		// module does after its port is opened.
		{"/dev/serial/by-id/usb-SimTech-if02-port0", answersAT(2)},
		{"/dev/serial/by-id/usb-SimTech-if03-port0", answersAT(0)},
		{"/dev/serial/by-id/usb-SimTech-if04-port0", &scriptedPort{}},
		{"/dev/serial/by-id/usb-ScanTool-OBDLink-if00-port0", &scriptedPort{replies: map[string]string{
			"ATI": "ATI\r\rELM327 v1.3a\r\r>",
		}}},
	}

	reports := make([]PortReport, 0, len(ports))
	for _, entry := range ports {
		report := ClassifyPort(entry.port, fastProbe)
		report.Device = entry.device
		reports = append(reports, report)
	}

	gps, obd, modem := SelectRoles(reports)
	if modem != "/dev/serial/by-id/usb-SimTech-if02-port0" {
		t.Fatalf("modem=%q, want the first control interface; without it the receiver can never be switched on", modem)
	}
	// Nothing streams, so the control port is the position source as well: it
	// answers +CGPSINFO once the receiver it just enabled has a fix.
	if gps != modem {
		t.Fatalf("gps=%q, want the control port %q as the fallback position source", gps, modem)
	}
	if obd != "/dev/serial/by-id/usb-ScanTool-OBDLink-if00-port0" {
		t.Fatalf("obd=%q, want the ELM adapter unaffected by the modem sweep", obd)
	}
	if StreamsNMEA(reports, gps) {
		t.Fatal("a powered-down receiver must not be recorded as streaming, or the enable step is skipped")
	}
}

// The five interfaces of one SIM7600 carry identical USB names, so only the probe
// result may decide which one is the GPS source.
func TestSelectRolesPrefersProbedPortsOverPosition(t *testing.T) {
	gps, obd, modem := SelectRoles([]PortReport{
		{Device: "/dev/serial/by-id/usb-SimTech-if00-port0"},
		{Device: "/dev/serial/by-id/usb-SimTech-if01-port0"},
		{Device: "/dev/serial/by-id/usb-SimTech-if02-port0", Modem: true},
		{Device: "/dev/serial/by-id/usb-SimTech-if03-port0", NMEA: true},
		{Device: "/dev/serial/by-id/usb-ScanTool-OBDLink-if00-port0", ELM: true},
	})
	if gps != "/dev/serial/by-id/usb-SimTech-if03-port0" {
		t.Fatalf("gps=%q, want the interface that actually streams NMEA", gps)
	}
	if obd != "/dev/serial/by-id/usb-ScanTool-OBDLink-if00-port0" {
		t.Fatalf("obd=%q", obd)
	}
	if modem != "/dev/serial/by-id/usb-SimTech-if02-port0" {
		t.Fatalf("modem=%q", modem)
	}
}

// A module that publishes no NMEA interface still answers position over AT.
func TestSelectRolesFallsBackToTheModemForPosition(t *testing.T) {
	gps, _, modem := SelectRoles([]PortReport{
		{Device: "/dev/ttyUSB3", Modem: true},
		{Device: "/dev/ttyUSB0", ELM: true},
	})
	if gps != "/dev/ttyUSB3" || modem != "/dev/ttyUSB3" {
		t.Fatalf("gps=%q modem=%q, want the modem used as the position source", gps, modem)
	}
}

// The interface that streams NMEA is frequently the control port too. It must be
// chosen for both jobs, and its stream is what the position is read from: polling
// returns whatever the module last stored, while the stream reports a fix as the
// receiver produces it.
func TestSelectRolesUsesOnePortForBothJobs(t *testing.T) {
	reports := []PortReport{
		{Device: "/dev/ttyUSB0", ELM: true},
		{Device: "/dev/ttyUSB1", NMEA: true, Modem: true},
	}
	gps, obd, modem := SelectRoles(reports)
	if gps != "/dev/ttyUSB1" || modem != "/dev/ttyUSB1" || obd != "/dev/ttyUSB0" {
		t.Fatalf("gps=%q obd=%q modem=%q", gps, obd, modem)
	}
	if !StreamsNMEA(reports, gps) {
		t.Fatal("the chosen GPS path streams, so its position must be read as a stream")
	}
	if StreamsNMEA(reports, "/dev/ttyUSB0") || StreamsNMEA(reports, "/dev/nothing") {
		t.Fatal("only a path the sweep saw streaming may be read as a stream")
	}
}

// A port that never answers must not stop the sweep. One interface of a cellular
// module blocked its open on real hardware, and every command that has to find its
// devices hung behind it, the telemetry service included.
func TestProbeAbandonsAPortThatNeverAnswers(t *testing.T) {
	// A path that cannot be opened stands in for one that never returns: both must
	// produce a report rather than nothing.
	useProbeHelper(t, "direct", "", "")
	started := time.Now()
	report := ProbeDevice("/dev/carhibou-nonexistent-port")
	if report.Device != "/dev/carhibou-nonexistent-port" || report.Error == "" {
		t.Fatalf("%+v, want a report naming the failure", report)
	}
	if report.NMEA || report.ELM || report.Modem {
		t.Fatalf("%+v, want no capabilities claimed", report)
	}
	if elapsed := time.Since(started); elapsed > probeTimeout {
		t.Fatalf("probe took %s, beyond its %s bound", elapsed, probeTimeout)
	}
}

// The sweep has to report every candidate, including the ones it gave up on, so
// SelectRoles sees a complete picture and the operator sees which port is at fault.
func TestSweepReportsEveryCandidateEvenWhenOneFails(t *testing.T) {
	useProbeHelper(t, "direct", "", "")
	seen := []string{}
	reports := ProbeAll(
		[]string{"/dev/carhibou-missing-a", "/dev/carhibou-missing-b"},
		func(report PortReport) { seen = append(seen, report.Device) },
	)
	if len(reports) != 2 || len(seen) != 2 {
		t.Fatalf("reports=%d announced=%d, want both candidates covered", len(reports), len(seen))
	}
}

// A timeout is useful only if the work that timed out is gone. The old in-process
// goroutine returned to its caller but retained the port, so every reacquisition
// sweep added another stuck owner until only a USB power cycle recovered it.
func TestTimedOutProbeReleasesResourcesBeforeTheNextRound(t *testing.T) {
	temporary := t.TempDir()
	lockPath := filepath.Join(temporary, "serial-port.lock")
	eventsPath := filepath.Join(temporary, "events")
	useProbeHelper(t, "lock", lockPath, eventsPath)

	previousTimeout := probeTimeout
	// The race runtime makes starting a second Go test process noticeably slow
	// on one core. Keep the timeout above that instrumentation overhead while
	// still proving the wedged child is killed on a short, deterministic bound.
	probeTimeout = 3 * time.Second
	t.Cleanup(func() { probeTimeout = previousTimeout })

	started := time.Now()
	firstRound := ProbeAll([]string{"/dev/wedged"}, nil)
	if len(firstRound) != 1 || !strings.Contains(firstRound[0].Error, "isolated probe was stopped") {
		t.Fatalf("first round=%+v, want an explicitly stopped timed-out probe", firstRound)
	}
	if elapsed := time.Since(started); elapsed > 5*time.Second {
		t.Fatalf("probe waited %s on a child that never returns", elapsed)
	}

	// Acquiring the same kernel lock proves the killed child was reaped and all
	// its descriptors were closed before ProbeDevice returned.
	lock, err := os.OpenFile(lockPath, os.O_CREATE|os.O_RDWR, 0o600)
	if err != nil {
		t.Fatal(err)
	}
	defer lock.Close()
	if err := syscall.Flock(int(lock.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		t.Fatalf("timed-out probe still owns its resource: %v", err)
	}
	if err := syscall.Flock(int(lock.Fd()), syscall.LOCK_UN); err != nil {
		t.Fatal(err)
	}

	// A later sweep uses the same resource. The helper rejects overlapping owners,
	// so this succeeds only when the first round cannot outlive its timeout.
	secondRound := ProbeAll([]string{"/dev/healthy"}, nil)
	if len(secondRound) != 1 || !secondRound[0].Modem || secondRound[0].Role != RoleModem {
		t.Fatalf("second round=%+v, want the next isolated probe to acquire the port", secondRound)
	}
	events, err := os.ReadFile(eventsPath)
	if err != nil {
		t.Fatal(err)
	}
	lines := strings.Split(strings.TrimSpace(string(events)), "\n")
	if len(lines) != 2 {
		t.Fatalf("events=%q, want two non-overlapping probe owners", events)
	}
	for index, wantDevice := range []string{"/dev/wedged", "/dev/healthy"} {
		var device string
		var processID int
		if _, err := fmt.Sscanf(lines[index], "start %s %d", &device, &processID); err != nil {
			t.Fatalf("cannot parse probe event %q: %v", lines[index], err)
		}
		if device != wantDevice {
			t.Fatalf("event %d device=%q, want %q", index, device, wantDevice)
		}
		if err := syscall.Kill(processID, 0); err != syscall.ESRCH {
			t.Fatalf("probe process %d still exists after ProbeDevice returned: %v", processID, err)
		}
	}
}

// The watchdog has to sit above the conversation it guards and not far above it:
// below, and a port about to answer is abandoned; far above, and a dead port costs
// more than it has to. Deriving it keeps the two from drifting apart.
func TestProbeTimeoutTracksTheConversationBudget(t *testing.T) {
	budget := defaultConversation.budget()
	if probeTimeout <= budget {
		t.Fatalf("timeout %s is not above the %s a healthy port may take", probeTimeout, budget)
	}
	if probeTimeout > budget*2 {
		t.Fatalf("timeout %s is far beyond the %s budget it guards", probeTimeout, budget)
	}
}

// A probe that cannot be launched must not be reported as a silent port. The
// child is the agent's own binary, so an update that replaces that file, or any
// host refusing the exec, would otherwise wipe out device discovery entirely
// while every cable was still in place.
func TestProbeFallsBackToAskingDirectlyWhenNoChildCanStart(t *testing.T) {
	previousProcess := probeProcess
	probeProcess = func(context.Context, string) (*exec.Cmd, error) {
		return nil, errors.New("executable no longer exists")
	}
	t.Cleanup(func() { probeProcess = previousProcess })

	previousOpen := openPort
	openPort = func(string) (serial.Port, error) {
		return &scriptedPort{replies: map[string]string{"AT\r": "AT\r\r\nOK\r\n"}}, nil
	}
	t.Cleanup(func() { openPort = previousOpen })

	report := ProbeDevice("/dev/carhibou-modem")
	if !report.Modem || report.Role != RoleModem {
		t.Fatalf("%+v, want the control port still identified without isolation", report)
	}
	if !strings.Contains(report.Error, "isolated probe could not start") {
		t.Fatalf("error=%q, want the loss of isolation recorded on the report", report.Error)
	}
}

const (
	probeHelperMode   = "CARHIBOU_TEST_PROBE_HELPER"
	probeHelperDevice = "CARHIBOU_TEST_PROBE_DEVICE"
	probeHelperLock   = "CARHIBOU_TEST_PROBE_LOCK"
	probeHelperEvents = "CARHIBOU_TEST_PROBE_EVENTS"
)

// useProbeHelper replaces the production self-exec command with this test
// binary's one-purpose child. It preserves the real process start/kill/wait path.
func useProbeHelper(t *testing.T, mode, lockPath, eventsPath string) {
	t.Helper()
	previous := probeProcess
	probeProcess = func(ctx context.Context, device string) (*exec.Cmd, error) {
		command := exec.CommandContext(ctx, os.Args[0], "-test.run=^TestIsolatedProbeProcess$")
		command.Env = append(os.Environ(),
			probeHelperMode+"="+mode,
			probeHelperDevice+"="+device,
			probeHelperLock+"="+lockPath,
			probeHelperEvents+"="+eventsPath,
		)
		return command, nil
	}
	t.Cleanup(func() { probeProcess = previous })
}

// TestIsolatedProbeProcess is entered only by useProbeHelper's child process.
// os.Exit prevents the go test harness from adding PASS text after the JSON result.
func TestIsolatedProbeProcess(t *testing.T) {
	mode := os.Getenv(probeHelperMode)
	if mode == "" {
		return
	}
	device := os.Getenv(probeHelperDevice)
	if mode == "direct" {
		if err := RunProbeChild(device, os.Stdout); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(2)
		}
		os.Exit(0)
	}
	if mode != "lock" {
		fmt.Fprintln(os.Stderr, "unknown helper mode", mode)
		os.Exit(2)
	}

	lock, err := os.OpenFile(os.Getenv(probeHelperLock), os.O_CREATE|os.O_RDWR, 0o600)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	if err := syscall.Flock(int(lock.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		fmt.Fprintln(os.Stderr, "overlapping probe retained the resource:", err)
		os.Exit(3)
	}
	events, err := os.OpenFile(os.Getenv(probeHelperEvents), os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o600)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	if _, err := fmt.Fprintf(events, "start %s %d\n", device, os.Getpid()); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	if err := events.Close(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	if device == "/dev/wedged" {
		for {
			time.Sleep(time.Hour)
		}
	}
	if err := json.NewEncoder(os.Stdout).Encode(PortReport{
		Device: device,
		Role:   RoleModem,
		Modem:  true,
	}); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	os.Exit(0)
}
