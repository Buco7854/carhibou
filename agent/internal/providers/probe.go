package providers

import (
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
type PortReport struct {
	Device   string     `json:"device"`
	Role     SerialRole `json:"role"`
	Identity string     `json:"identity,omitempty"`
	Error    string     `json:"error,omitempty"`
}

// probeConversation is the minimum a port has to do to be identified. Windows are
// deliberately short: a Pi Zero probes every candidate in sequence at startup and
// a slow sweep would delay the first telemetry sample.
type probeConversation struct {
	listen  time.Duration
	command time.Duration
}

var defaultConversation = probeConversation{listen: 900 * time.Millisecond, command: 700 * time.Millisecond}

// ClassifyPort identifies one already-open port.
//
// Order matters. Listening first costs nothing on a talkative port and identifies
// an NMEA stream without writing anything to hardware whose purpose is unknown.
// Only a silent port is then asked, ELM first because an OBD adapter answers ATI
// immediately while a modem needs a moment.
func ClassifyPort(port serial.Port, timing probeConversation) (SerialRole, string) {
	if sentence, ok := listenForNMEA(port, timing.listen); ok {
		return RoleNMEA, sentence
	}
	if identity, ok := ask(port, "ATI", timing.command, func(reply string) bool {
		upper := strings.ToUpper(reply)
		return strings.Contains(upper, "ELM") || strings.Contains(upper, "STN") || strings.Contains(upper, "OBD")
	}); ok {
		return RoleELM, identity
	}
	if identity, ok := ask(port, "AT", timing.command, func(reply string) bool {
		return strings.Contains(strings.ToUpper(reply), "OK")
	}); ok {
		return RoleModem, identity
	}
	return RoleUnknown, ""
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

// ProbeDevice opens one path and reports what it speaks.
func ProbeDevice(device string) PortReport {
	port, err := serial.Open(device, &serial.Mode{BaudRate: 115200})
	if err != nil {
		return PortReport{Device: device, Role: RoleUnknown, Error: err.Error()}
	}
	defer port.Close()
	if err := port.SetReadTimeout(200 * time.Millisecond); err != nil {
		return PortReport{Device: device, Role: RoleUnknown, Error: err.Error()}
	}
	role, identity := ClassifyPort(port, defaultConversation)
	return PortReport{Device: device, Role: role, Identity: identity}
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

// SelectRoles picks the GPS and OBD paths from a probe sweep.
//
// A port publishing NMEA is preferred for GPS because it needs no polling; a modem
// control port is the fallback, since it can still answer position over AT and can
// switch the receiver on. An unprobed name hint never overrides a probe result.
func SelectRoles(reports []PortReport) (gps string, obd string, modem string) {
	ordered := append([]PortReport(nil), reports...)
	sort.SliceStable(ordered, func(left, right int) bool { return ordered[left].Device < ordered[right].Device })
	for _, report := range ordered {
		switch report.Role {
		case RoleNMEA:
			if gps == "" {
				gps = report.Device
			}
		case RoleELM:
			if obd == "" {
				obd = report.Device
			}
		case RoleModem:
			if modem == "" {
				modem = report.Device
			}
		}
	}
	if gps == "" {
		gps = modem
	}
	return gps, obd, modem
}
