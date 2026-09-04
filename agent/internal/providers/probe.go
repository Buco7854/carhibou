package providers

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"sort"
	"strings"
	"time"

	"go.bug.st/serial"
)

// SerialRole is what a port turned out to speak, established by asking it rather
// than by trusting its USB product name. A SIM7600 publishes five interfaces with
// identical names and only some of them answer, so names cannot decide this.
type SerialRole string

const (
	RoleUnknown SerialRole = "unknown"
	RoleNMEA    SerialRole = "nmea"
	RoleELM     SerialRole = "elm"
	RoleModem   SerialRole = "modem"
)

// PortReport is the outcome of probing one serial path.
//
// The capabilities are deliberately not exclusive. A cellular module publishes an
// interface that streams NMEA and also accepts AT, and recording only the first
// answer meant such a port was filed as a receiver and never asked whether it
// could switch that receiver on. Which interface index carries which capability
// varies by module and firmware, so nothing here may be inferred from the name.
type PortReport struct {
	Device   string     `json:"device"`
	Role     SerialRole `json:"role"`
	NMEA     bool       `json:"nmea,omitempty"`
	ELM      bool       `json:"elm,omitempty"`
	Modem    bool       `json:"modem,omitempty"`
	Identity string     `json:"identity,omitempty"`
	Error    string     `json:"error,omitempty"`
}

// primaryRole is the single label to show for a port that may do several things.
func primaryRole(report PortReport) SerialRole {
	switch {
	case report.ELM:
		return RoleELM
	case report.NMEA:
		return RoleNMEA
	case report.Modem:
		return RoleModem
	}
	return RoleUnknown
}

// probeConversation is the minimum a port has to do to be identified. Windows are
// deliberately short: a Pi Zero probes every candidate in sequence at startup and
// a slow sweep would delay the first telemetry sample.
type probeConversation struct {
	listen       time.Duration
	identity     time.Duration
	modemCommand time.Duration
	// modemAttempts is how many times AT is asked inside its window. A SIM7600
	// control interface routinely ignores the first command after being opened;
	// asking once recorded that wake-up loss as "this port is not a modem", which
	// is how the only interface able to switch GNSS back on went missing.
	modemAttempts int
}

// The listen window is the floor here: a receiver emits its sentences in a burst
// about once a second, so a port opened just after one has to be given long enough
// to hear the next. ELM adapters normally answer ATI in milliseconds. SIM7600
// control interfaces can take longer to answer their first AT after being opened,
// especially on a Pi Zero, so that final question gets its own larger window.
// Completed replies stop either window immediately, keeping a healthy sweep fast.
var defaultConversation = probeConversation{
	listen:        1100 * time.Millisecond,
	identity:      600 * time.Millisecond,
	modemCommand:  1500 * time.Millisecond,
	modemAttempts: 3,
}

// budget is the longest a probe can legitimately take: listen, then ask twice,
// then leave the port alone after closing it.
//
// This is an exact figure rather than an estimate, because every phase reads
// against its own deadline. It used to be neither: each phase set one fixed read
// timeout and re-checked the clock only between reads, so a silent port overran
// every window by up to a full read. Three phases of overrun pushed the probe
// past the watchdog guarding it, and the port that has to run all three phases
// before answering is exactly the modem control interface.
func (timing probeConversation) budget() time.Duration {
	return timing.listen + timing.identity + timing.modemCommand + portSettle
}

// ClassifyPort reports what one already-open port turns out to do.
//
// Listening comes first because it costs nothing on a talkative port and needs no
// write to hardware whose purpose is unknown, and a port that streams NMEA has
// answered the question by itself: it is classified and left alone, without ever
// being written to. Asking it for AT as well used to be justified by wanting the
// interface that can switch the receiver on, but SelectRoles finds that among the
// ports that did not stream, and a cellular module is at its most fragile when
// its NMEA interface is sent commands. Sweeps now run on a reacquisition backoff
// rather than only at startup, so that traffic repeats for as long as any source
// is missing.
//
// ELM is asked before AT and ends the enquiry, because an OBD adapter answers
// plain AT too and would otherwise be mistaken for a modem.
func ClassifyPort(port serial.Port, timing probeConversation) PortReport {
	report := PortReport{}
	if sentence, ok := listenForNMEA(port, timing.listen); ok {
		report.NMEA = true
		report.Identity = sentence
		report.Role = primaryRole(report)
		return report
	}
	if identity, ok := ask(port, "ATI", timing.identity, 1, func(reply string) bool {
		upper := strings.ToUpper(reply)
		return strings.Contains(upper, "ELM") || strings.Contains(upper, "STN") || strings.Contains(upper, "OBD")
	}); ok {
		report.ELM = true
		report.Identity = identity
		report.Role = primaryRole(report)
		return report
	}
	if _, ok := ask(port, "AT", timing.modemCommand, timing.modemAttempts, func(reply string) bool {
		return strings.Contains(strings.ToUpper(reply), "OK")
	}); ok {
		report.Modem = true
	}
	report.Role = primaryRole(report)
	return report
}

// readUntil hands every chunk that arrives before the deadline to consume, and
// stops as soon as consume is satisfied or the deadline passes.
//
// The read timeout is narrowed to the time actually remaining rather than left at
// a fixed slice, so a phase ends when its window ends. With a fixed slice the last
// read of a silent port started just under the deadline and still ran its full
// length, overrunning every phase; that hidden cost is what the probe watchdog
// eventually collided with. A long timeout costs nothing on a port that talks,
// because a read returns as soon as bytes arrive.
func readUntil(port serial.Port, deadline time.Time, buffer []byte, consume func(string) bool) bool {
	for {
		remaining := time.Until(deadline)
		if remaining <= 0 {
			return false
		}
		if err := port.SetReadTimeout(remaining); err != nil {
			return false
		}
		count, err := port.Read(buffer)
		if count > 0 && consume(string(buffer[:count])) {
			return true
		}
		if err != nil {
			return false
		}
	}
}

func listenForNMEA(port serial.Port, window time.Duration) (string, bool) {
	buffer := make([]byte, 256)
	pending := ""
	sentence := ""
	readUntil(port, time.Now().Add(window), buffer, func(chunk string) bool {
		pending += chunk
		for {
			index := strings.IndexAny(pending, "\r\n")
			if index < 0 {
				break
			}
			line := strings.TrimSpace(pending[:index])
			pending = pending[index+1:]
			if validChecksum(line) {
				sentence = line
				return true
			}
		}
		if len(pending) > maxPending {
			pending = ""
		}
		return false
	})
	return sentence, sentence != ""
}

// ask puts one question to a port and reports whether the reply was the expected
// one, repeating the question up to attempts times inside the window.
//
// Repetition exists for the SIM7600 control interface, which commonly swallows the
// first command sent after its port is opened: an interactive terminal hides that
// because the operator simply presses return again. The agent's own modem client
// already wakes the port this way before every state change, and the sweep that
// has to find that port in the first place must be no less patient, or the port is
// filed as unknown and the receiver can never be switched back on.
//
// A reply that is complete but wrong ends the enquiry immediately: repeating the
// question cannot change an answer the port has already given.
func ask(port serial.Port, command string, window time.Duration, attempts int, accept func(string) bool) (string, bool) {
	if attempts < 1 {
		attempts = 1
	}
	buffer := make([]byte, 256)
	deadline := time.Now().Add(window)
	slice := window / time.Duration(attempts)
	for attempt := 0; attempt < attempts; attempt++ {
		if !time.Now().Before(deadline) {
			break
		}
		if err := port.ResetInputBuffer(); err != nil {
			return "", false
		}
		if _, err := port.Write([]byte(command + "\r")); err != nil {
			return "", false
		}
		attemptDeadline := time.Now().Add(slice)
		if attemptDeadline.After(deadline) {
			attemptDeadline = deadline
		}
		reply := ""
		answered := false
		readUntil(port, attemptDeadline, buffer, func(chunk string) bool {
			reply += chunk
			if accept(reply) {
				answered = true
				return true
			}
			// ATI on a modem commonly returns its model and OK. That is a
			// complete, useful rejection of the ELM question, so move straight
			// on to AT instead of spending the rest of the identity window.
			return isFinalResult(reply) || strings.Contains(reply, ">")
		})
		if answered {
			return firstMeaningfulLine(reply, command), true
		}
		if isFinalResult(reply) || strings.Contains(reply, ">") {
			return "", false
		}
	}
	return "", false
}

func firstMeaningfulLine(reply, command string) string {
	for _, line := range responseLines(reply, command) {
		if !strings.EqualFold(line, "OK") {
			return line
		}
	}
	return "OK"
}

// portSettle is how long a probed interface is left alone after being closed.
//
// A cellular module publishes several interfaces from one USB serial driver, and
// reopening one immediately after closing it is what that driver handles worst:
// on a SIM7600 the second open never returned, hanging every diagnostic command
// the moment the sweep finished. The sweep is the only place that closes and
// reopens ports in quick succession, so the cost is a fraction of a second once.
const portSettle = 200 * time.Millisecond

// probeTimeout bounds one isolated probe process.
//
// Opening a serial path can block in the kernel with nothing in Go able to cancel
// it. A cellular module publishes interfaces that are not conversational character
// streams at all — diagnostic, PPP, audio — and one of them wedged a sweep on real
// hardware, taking down every command that has to find its devices, the service
// included. The probe therefore runs in a child process. Timing out kills and
// reaps that process before returning, which closes its serial descriptor and
// prevents later reacquisition sweeps from piling up behind abandoned probes.
//
// It is derived from the conversation rather than chosen, so the two cannot drift
// apart: a watchdog below the budget abandons ports that were about to answer,
// which is precisely how a working SIM7600 control interface came to be reported
// as giving "no answer" while a terminal on the same port answered at once.
//
// The allowance above the budget is deliberately generous, and costs nothing. A
// silent port is not what it guards: that child finishes its own conversation and
// exits at the budget. It guards a child wedged in the kernel, which is rare, and
// against fork, exec and scheduling of the agent binary on one slow core that is
// also decoding CAN frames. Being mean here buys no speed and risks the only
// failure that matters.
const probeStartupAllowance = 3 * time.Second

var probeTimeout = defaultConversation.budget() + probeStartupAllowance

// openPort is the child-side seam used by direct classification tests.
var openPort = func(device string) (serial.Port, error) {
	return serial.Open(device, &serial.Mode{BaudRate: 115200})
}

// ProbeChildCommand is the private command the agent executable dispatches to
// RunProbeChild. It is exported so the executable and this package cannot disagree
// on a magic string, but it is intentionally omitted from user-facing help.
const ProbeChildCommand = "__probe-device"

// probeProcess is a seam for executing a test helper. Production always invokes
// the running agent binary, so the child is the same version as its parent.
var probeProcess = func(ctx context.Context, device string) (*exec.Cmd, error) {
	executable, err := os.Executable()
	if err != nil {
		return nil, err
	}
	return exec.CommandContext(ctx, executable, ProbeChildCommand, device), nil
}

// ProbeDevice opens one path in an isolated process and reports what it speaks.
//
// cmd.Run waits for a killed child to be reaped. Consequently this function never
// reports a timeout while an abandoned probe can still own the serial path.
func ProbeDevice(device string) PortReport {
	ctx, cancel := context.WithTimeout(context.Background(), probeTimeout)
	defer cancel()
	command, err := probeProcess(ctx, device)
	if err != nil {
		return probeWithoutIsolation(device, err)
	}
	var stdout, stderr bytes.Buffer
	command.Stdout = &stdout
	command.Stderr = &stderr
	err = command.Run()
	if ctx.Err() == context.DeadlineExceeded {
		return PortReport{
			Device: device,
			Role:   RoleUnknown,
			Error:  fmt.Sprintf("no answer within %s; the isolated probe was stopped", probeTimeout),
		}
	}
	if err != nil {
		var exited *exec.ExitError
		if !errors.As(err, &exited) {
			// The child never got as far as running. Its own binary is what is
			// re-executed, so this is what an agent whose file has been replaced
			// underneath it sees, and it would otherwise be reported as every
			// port being silent — total loss of discovery, with no hardware fault.
			return probeWithoutIsolation(device, err)
		}
		detail := strings.TrimSpace(stderr.String())
		if detail != "" {
			err = fmt.Errorf("%w: %s", err, detail)
		}
		return PortReport{Device: device, Role: RoleUnknown, Error: fmt.Sprintf("isolated probe failed: %v", err)}
	}
	var report PortReport
	if err := json.Unmarshal(bytes.TrimSpace(stdout.Bytes()), &report); err != nil {
		return PortReport{Device: device, Role: RoleUnknown, Error: fmt.Sprintf("invalid isolated probe result: %v", err)}
	}
	if report.Device != device {
		return PortReport{
			Device: device,
			Role:   RoleUnknown,
			Error:  fmt.Sprintf("isolated probe reported unexpected device %q", report.Device),
		}
	}
	return report
}

// probeWithoutIsolation asks the port directly when no child process could be
// started to ask on its behalf.
//
// Isolation exists to survive a serial syscall that wedges, which is rare; being
// unable to launch the probe at all would otherwise report every port as silent,
// which is certain and much worse. Degrading to the direct question keeps device
// discovery working, and the reason is recorded on the report either way.
func probeWithoutIsolation(device string, cause error) PortReport {
	report := probeDevice(openPort, device)
	if report.Error == "" {
		report.Error = fmt.Sprintf("probed directly; the isolated probe could not start: %v", cause)
	}
	return report
}

// ProbeDeviceInProcess is the child-side primitive. Normal callers must use
// ProbeDevice so a stuck serial syscall can be terminated without a reboot.
func ProbeDeviceInProcess(device string) PortReport {
	return probeDevice(openPort, device)
}

// RunProbeChild performs one direct probe and writes its machine-readable result.
// The main package dispatches ProbeChildCommand here before any service work.
func RunProbeChild(device string, output io.Writer) error {
	return json.NewEncoder(output).Encode(ProbeDeviceInProcess(device))
}

// ProbeKnownDevice classifies a port that was an OBD adapter last time.
//
// An adapter that has just been reset, or was released by a process that stopped
// a moment ago, answers nothing for a short while and classifies as unknown. One
// retry after a settle delay is the difference between recovering the device and
// starting a full sweep for hardware that never moved.
func ProbeKnownDevice(device string) PortReport {
	report := ProbeDevice(device)
	if report.Role != RoleUnknown {
		return report
	}
	time.Sleep(knownDeviceSettle)
	return ProbeDevice(device)
}

// knownDeviceSettle is how long a formerly-known port is given to finish coming
// back before its second and final chance.
const knownDeviceSettle = 2 * time.Second

func probeDevice(open func(string) (serial.Port, error), device string) PortReport {
	port, err := open(device)
	if err != nil {
		return PortReport{Device: device, Role: RoleUnknown, Error: err.Error()}
	}
	defer func() {
		port.Close()
		time.Sleep(portSettle)
	}()
	// Each phase of the conversation narrows this to the time its own window has
	// left, so this value is only a ceiling and an early check that the port
	// accepts one at all. It is deliberately not a small slice: a fixed slice
	// here was what let every phase overrun its window.
	if err := port.SetReadTimeout(defaultConversation.budget()); err != nil {
		return PortReport{Device: device, Role: RoleUnknown, Error: err.Error()}
	}
	report := ClassifyPort(port, defaultConversation)
	report.Device = device
	return report
}

// ProbeAll classifies every candidate, sequentially so one core is never shared
// between several open serial ports.
//
// A sweep is seconds of work per port with nothing to show for it, so onReport is
// called as each one finishes. A diagnostic command that prints nothing while it
// works is indistinguishable from one that has hung.
func ProbeAll(devices []string, onReport func(PortReport)) []PortReport {
	reports := make([]PortReport, 0, len(devices))
	for _, device := range devices {
		report := ProbeDevice(device)
		if onReport != nil {
			onReport(report)
		}
		reports = append(reports, report)
	}
	return reports
}

// SelectRoles picks the GPS, OBD and modem paths from a probe sweep.
//
// A port publishing NMEA is preferred for GPS because it needs no polling; a modem
// control port is the fallback, since it can still answer position over AT. The
// same port may fill both jobs, and often does: the interface that streams NMEA is
// frequently the one that accepts the command switching that stream on. An
// unprobed name hint never overrides a probe result.
func SelectRoles(reports []PortReport) (gps string, obd string, modem string) {
	ordered := append([]PortReport(nil), reports...)
	sort.SliceStable(ordered, func(left, right int) bool { return ordered[left].Device < ordered[right].Device })
	for _, report := range ordered {
		if report.NMEA && gps == "" {
			gps = report.Device
		}
		if report.ELM && obd == "" {
			obd = report.Device
		}
		if report.Modem && modem == "" {
			modem = report.Device
		}
	}
	if gps == "" {
		gps = modem
	}
	return gps, obd, modem
}

// StreamsNMEA reports whether a swept path publishes sentences of its own, which
// decides whether its position is read as a stream or polled over AT.
func StreamsNMEA(reports []PortReport, device string) bool {
	for _, report := range reports {
		if report.Device == device {
			return report.NMEA
		}
	}
	return false
}
