package providers

import (
	"fmt"
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
	listen  time.Duration
	command time.Duration
}

var defaultConversation = probeConversation{listen: 900 * time.Millisecond, command: 700 * time.Millisecond}

// ClassifyPort reports everything one already-open port turns out to do.
//
// Listening comes first because it costs nothing on a talkative port and needs no
// write to hardware whose purpose is unknown. It is not the end of the enquiry: a
// port that streams NMEA is still asked whether it accepts AT, which is the only
// way to find the interface that can switch the receiver on.
//
// ELM is asked before AT and ends the enquiry, because an OBD adapter answers
// plain AT too and would otherwise be mistaken for a modem.
func ClassifyPort(port serial.Port, timing probeConversation) PortReport {
	report := PortReport{}
	if sentence, ok := listenForNMEA(port, timing.listen); ok {
		report.NMEA = true
		report.Identity = sentence
	}
	if identity, ok := ask(port, "ATI", timing.command, func(reply string) bool {
		upper := strings.ToUpper(reply)
		return strings.Contains(upper, "ELM") || strings.Contains(upper, "STN") || strings.Contains(upper, "OBD")
	}); ok {
		report.ELM = true
		report.Identity = identity
		report.Role = primaryRole(report)
		return report
	}
	if _, ok := ask(port, "AT", timing.command, func(reply string) bool {
		return strings.Contains(strings.ToUpper(reply), "OK")
	}); ok {
		report.Modem = true
	}
	report.Role = primaryRole(report)
	return report
}

func listenForNMEA(port serial.Port, window time.Duration) (string, bool) {
	buffer := make([]byte, 256)
	deadline := time.Now().Add(window)
	pending := ""
	for time.Now().Before(deadline) {
		count, err := port.Read(buffer)
		if count > 0 {
			pending += string(buffer[:count])
			for {
				index := strings.IndexAny(pending, "\r\n")
				if index < 0 {
					break
				}
				line := strings.TrimSpace(pending[:index])
				pending = pending[index+1:]
				if validChecksum(line) {
					return line, true
				}
			}
			if len(pending) > maxPending {
				pending = ""
			}
		}
		if err != nil {
			return "", false
		}
	}
	return "", false
}

func ask(port serial.Port, command string, window time.Duration, accept func(string) bool) (string, bool) {
	if err := port.ResetInputBuffer(); err != nil {
		return "", false
	}
	if _, err := port.Write([]byte(command + "\r")); err != nil {
		return "", false
	}
	buffer := make([]byte, 256)
	deadline := time.Now().Add(window)
	reply := ""
	for time.Now().Before(deadline) {
		count, err := port.Read(buffer)
		if count > 0 {
			reply += string(buffer[:count])
			if accept(reply) {
				return firstMeaningfulLine(reply, command), true
			}
		}
		if err != nil {
			break
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

// probeTimeout bounds one port.
//
// Opening a serial path can block in the kernel with nothing in Go able to cancel
// it. A cellular module publishes interfaces that are not conversational character
// streams at all — diagnostic, PPP, audio — and one of them wedged a sweep on real
// hardware, taking down every command that has to find its devices, the service
// included. A port that has not answered by now is abandoned so the rest of the
// sweep carries on without it. The goroutine left behind is stuck in a syscall and
// cannot be reclaimed, which is why the sweep runs once rather than repeatedly.
var probeTimeout = 5 * time.Second

// openPort is a seam: a device that never returns from open cannot be created on
// demand, and the abandonment path is the whole point of the timeout.
var openPort = func(device string) (serial.Port, error) {
	return serial.Open(device, &serial.Mode{BaudRate: 115200})
}

// ProbeDevice opens one path and reports what it speaks, or gives up on it.
func ProbeDevice(device string) PortReport {
	// The opener is settled here rather than inside the goroutine, because that
	// goroutine outlives this call whenever a port has to be abandoned.
	open := openPort
	answered := make(chan PortReport, 1)
	go func() { answered <- probeDevice(open, device) }()
	select {
	case report := <-answered:
		return report
	case <-time.After(probeTimeout):
		return PortReport{
			Device: device,
			Role:   RoleUnknown,
			Error:  fmt.Sprintf("no answer within %s; the port was left alone", probeTimeout),
		}
	}
}

func probeDevice(open func(string) (serial.Port, error), device string) PortReport {
	port, err := open(device)
	if err != nil {
		return PortReport{Device: device, Role: RoleUnknown, Error: err.Error()}
	}
	defer func() {
		port.Close()
		time.Sleep(portSettle)
	}()
	if err := port.SetReadTimeout(200 * time.Millisecond); err != nil {
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
