package providers

import (
	"testing"
	"time"
)

func TestCANAndStandardOBDParsing(t *testing.T) {
	frame, err := ParseCANFrame("374 8 96 00 00 00 00 00 00 00", 12.5)
	if err != nil {
		t.Fatal(err)
	}
	if frame.CANID != 0x374 || frame.Data[0] != 0x96 {
		t.Fatalf("frame=%#v", frame)
	}
	if _, err := ParseCANFrame("374 8 01 02", 0); err == nil {
		t.Fatal("bad DLC accepted")
	}
	payload := ParseOBDResponse(1, 0x0C, []string{"7E8 04 41 0C 1A F8"})
	value, err := StandardPIDs[0x0C].Decode(payload)
	if err != nil || value != 1726 {
		t.Fatalf("rpm=%v err=%v", value, err)
	}
	if vin := ParseVIN([]string{"7E8 10 14 49 02 01 56 46 33", "7E8 21 31 58 58 58 58 58 58", "7E8 22 58 58 58 58 58 58 58"}); vin != "VF31XXXXXXXXXXXXX" {
		t.Fatalf("vin=%s", vin)
	}
	codes := ParseDTC([]string{"7E8 06 43 01 33 C1 23 00"})
	if len(codes) != 2 || codes[0] != "P0133" || codes[1] != "U0123" {
		t.Fatalf("codes=%#v", codes)
	}
}

// silentPort answers nothing and, like a real port, spends its whole read timeout
// doing so. The duration is what makes this a regression test: the reply used to
// be collected with a bufio.Reader, which counts the zero-length read of a serial
// timeout as progress and retries it a hundred times before reporting one. Each
// command therefore burned a hundred read timeouts instead of one, which at the
// two seconds this adapter was opened with is over three minutes per command, and
// Connect issues five of them. That is what "obd-info never answers" was.
type silentPort struct {
	scriptedPort
	readTimeout time.Duration
}

func (port *silentPort) Read([]byte) (int, error) {
	time.Sleep(port.readTimeout)
	return 0, nil
}

func TestCommandFailsWithinItsWindowWhenTheAdapterIsSilent(t *testing.T) {
	adapter := NewOBDAdapter("scripted")
	adapter.port = &silentPort{readTimeout: 20 * time.Millisecond}
	adapter.CommandWindow = 150 * time.Millisecond

	started := time.Now()
	if _, err := adapter.Command("ATI", 0); err == nil {
		t.Fatal("expected a silent adapter to report a timeout")
	}
	// A hundred retries of this port's read timeout would be two seconds.
	if elapsed := time.Since(started); elapsed > time.Second {
		t.Fatalf("command took %s, which is far beyond its %s window", elapsed, adapter.CommandWindow)
	}
}

func TestCommandReadsOneReplyAtATime(t *testing.T) {
	adapter := NewOBDAdapter("scripted")
	adapter.port = &scriptedPort{replies: map[string]string{"ATI": "ATI\r\rELM327 v1.3a\r\r>"}}
	adapter.CommandWindow = time.Second

	lines, err := adapter.Command("ATI", 0)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(lines) != 1 || lines[0] != "ELM327 v1.3a" {
		t.Fatalf("expected the identity line alone, got %#v", lines)
	}
}

// An adapter with no vehicle behind it still answers, so a null VIN and an empty
// fault list mean nothing on their own. Separating the adapter's own replies from
// the vehicle's is what makes a silent car diagnosable.
func TestVehicleAnsweredSeparatesTheAdapterFromTheCar(t *testing.T) {
	silent := [][]string{
		{"NO DATA"},
		{"SEARCHING..."},
		{"SEARCHING...", "UNABLE TO CONNECT"},
		{"STOPPED"},
		{""},
		{},
	}
	for _, lines := range silent {
		if VehicleAnswered(lines) {
			t.Fatalf("%q is the adapter speaking for itself, not the vehicle", lines)
		}
	}
	answered := [][]string{
		{"49 02 01 00 00 00 31"},
		{"SEARCHING...", "49 02 01 00 00 00 31"},
		{"43 01 33 00 00"},
	}
	for _, lines := range answered {
		if !VehicleAnswered(lines) {
			t.Fatalf("%q came from the vehicle", lines)
		}
	}
}

func TestVoltageAndProtocolComeFromTheAdapter(t *testing.T) {
	adapter := NewOBDAdapter("scripted")
	adapter.port = &scriptedPort{replies: map[string]string{
		"ATRV": "ATRV\r12.4V\r\r>",
		"ATDP": "ATDP\rISO 15765-4 (CAN 11/500)\r\r>",
	}}
	adapter.CommandWindow = time.Second

	voltage, err := adapter.Voltage()
	if err != nil || voltage != "12.4V" {
		t.Fatalf("voltage=%q err=%v", voltage, err)
	}
	protocol, err := adapter.Protocol()
	if err != nil || protocol != "ISO 15765-4 (CAN 11/500)" {
		t.Fatalf("protocol=%q err=%v", protocol, err)
	}
}
