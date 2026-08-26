package providers

import (
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
	role, identity := ClassifyPort(port, fastProbe)
	if role != RoleNMEA {
		t.Fatalf("role=%q identity=%q, want nmea", role, identity)
	}
}

func TestClassifyIdentifiesAnELMAdapter(t *testing.T) {
	port := &scriptedPort{replies: map[string]string{"ATI": "ATI\r\rELM327 v1.3a\r\r>"}}
	role, identity := ClassifyPort(port, fastProbe)
	if role != RoleELM || identity != "ELM327 v1.3a" {
		t.Fatalf("role=%q identity=%q, want an ELM adapter", role, identity)
	}
}

func TestClassifyIdentifiesAModemControlPort(t *testing.T) {
	port := &scriptedPort{replies: map[string]string{"AT\r": "AT\r\r\nOK\r\n"}}
	role, _ := ClassifyPort(port, fastProbe)
	if role != RoleModem {
		t.Fatalf("role=%q, want modem", role)
	}
}

func TestClassifyLeavesASilentPortUnknown(t *testing.T) {
	role, _ := ClassifyPort(&scriptedPort{}, fastProbe)
	if role != RoleUnknown {
		t.Fatalf("role=%q, want unknown", role)
	}
}

// The five interfaces of one SIM7600 carry identical USB names, so only the probe
// result may decide which one is the GPS source.
func TestSelectRolesPrefersProbedPortsOverPosition(t *testing.T) {
	gps, obd, modem := SelectRoles([]PortReport{
		{Device: "/dev/serial/by-id/usb-SimTech-if00-port0", Role: RoleUnknown},
		{Device: "/dev/serial/by-id/usb-SimTech-if01-port0", Role: RoleUnknown},
		{Device: "/dev/serial/by-id/usb-SimTech-if02-port0", Role: RoleModem},
		{Device: "/dev/serial/by-id/usb-SimTech-if03-port0", Role: RoleNMEA},
		{Device: "/dev/serial/by-id/usb-ScanTool-OBDLink-if00-port0", Role: RoleELM},
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
		{Device: "/dev/ttyUSB3", Role: RoleModem},
		{Device: "/dev/ttyUSB0", Role: RoleELM},
	})
	if gps != "/dev/ttyUSB3" || modem != "/dev/ttyUSB3" {
		t.Fatalf("gps=%q modem=%q, want the modem used as the position source", gps, modem)
	}
}
