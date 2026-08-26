package providers

import (
	"errors"
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

var fastProbe = probeConversation{listen: 60 * time.Millisecond, command: 60 * time.Millisecond}

func TestClassifyIdentifiesAnNMEAStreamWithoutWriting(t *testing.T) {
	port := &scriptedPort{stream: nmeaSentence("GPGGA,120000.00,4851.0000,N,00220.0000,E,1,08,1.0,89.6,M,,,,") + "\r\n"}
	report := ClassifyPort(port, fastProbe)
	if !report.NMEA || report.Role != RoleNMEA {
		t.Fatalf("%+v, want nmea", report)
	}
}

// The interface that streams sentences is often the one that accepts the command
// switching that stream on. Stopping at the first answer left the agent holding a
// receiver it had no way to power up, and which interface index carries which
// capability varies by module, so it cannot be assumed either.
func TestClassifyKeepsAskingAfterFindingAnNMEAStream(t *testing.T) {
	port := &scriptedPort{
		stream:  nmeaSentence("GPGGA,120000.00,4851.0000,N,00220.0000,E,1,08,1.0,89.6,M,,,,") + "\r\n",
		replies: map[string]string{"AT\r": "AT\r\r\nOK\r\n"},
	}
	report := ClassifyPort(port, fastProbe)
	if !report.NMEA || !report.Modem {
		t.Fatalf("%+v, want a port that both streams and accepts AT", report)
	}
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

func TestClassifyLeavesASilentPortUnknown(t *testing.T) {
	if report := ClassifyPort(&scriptedPort{}, fastProbe); report.Role != RoleUnknown {
		t.Fatalf("%+v, want unknown", report)
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
	started := time.Now()
	report := ProbeDevice("/dev/vehinode-nonexistent-port")
	if report.Device != "/dev/vehinode-nonexistent-port" || report.Error == "" {
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
	seen := []string{}
	reports := ProbeAll(
		[]string{"/dev/vehinode-missing-a", "/dev/vehinode-missing-b"},
		func(report PortReport) { seen = append(seen, report.Device) },
	)
	if len(reports) != 2 || len(seen) != 2 {
		t.Fatalf("reports=%d announced=%d, want both candidates covered", len(reports), len(seen))
	}
}

// The port that wedged real hardware blocked inside open, where no timeout in the
// serial library applies and nothing in Go can cancel the syscall.
func TestProbeGivesUpOnAPortWhoseOpenNeverReturns(t *testing.T) {
	blocked := make(chan struct{})
	t.Cleanup(func() { close(blocked) })

	previousOpen, previousTimeout := openPort, probeTimeout
	openPort = func(string) (serial.Port, error) {
		<-blocked
		// Released only when the test ends. Failing rather than returning a nil
		// port keeps the abandoned goroutine on the same path a real open error
		// takes, instead of one no serial device produces.
		return nil, errors.New("released at the end of the test")
	}
	probeTimeout = 80 * time.Millisecond
	t.Cleanup(func() { openPort, probeTimeout = previousOpen, previousTimeout })

	started := time.Now()
	report := ProbeDevice("/dev/wedged")
	if report.Error == "" {
		t.Fatalf("%+v, want the abandonment recorded", report)
	}
	if elapsed := time.Since(started); elapsed > time.Second {
		t.Fatalf("probe waited %s on a port that never opens", elapsed)
	}
	// The sweep must keep going, which is the reason for abandoning it at all.
	if reports := ProbeAll([]string{"/dev/wedged", "/dev/wedged-too"}, nil); len(reports) != 2 {
		t.Fatalf("got %d reports, want both candidates covered", len(reports))
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
