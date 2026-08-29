package providers

import (
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/Buco7854/carhibou/agent/internal/model"
	"go.bug.st/serial"
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

func TestCANParsingKeepsFramesWithDataErrorSuffix(t *testing.T) {
	tests := []struct {
		line  string
		canID int
		first byte
	}{
		{"374 8F 90 9D FE 4F 4B 47 14 <DATA ERROR", 0x374, 0x8F},
		{"373 BB BB 7F 4E 0C 65 00 16 <DATA ERROR", 0x373, 0xBB},
		{"412 FE 00 01 19 7A 00 21 12 <DATA ERROR", 0x412, 0xFE},
		{"298 43 42 4A 42 43 00 27 10 <DATA ERROR", 0x298, 0x43},
	}
	for _, test := range tests {
		frame, err := ParseCANFrame(test.line, 1)
		if err != nil {
			t.Fatalf("ParseCANFrame(%q): %v", test.line, err)
		}
		if frame.CANID != test.canID || len(frame.Data) != 8 || frame.Data[0] != test.first {
			t.Fatalf("ParseCANFrame(%q)=%#v", test.line, frame)
		}
	}
}

func TestDataErrorMarkerIsCountedWithoutDiscardingItsFrame(t *testing.T) {
	report := MonitorReport{}
	frames := 0
	observeMonitorLine(
		"374 8F 90 9D FE 4F 4B 47 14 <DATA ERROR",
		func(model.CANFrame) { frames++ },
		&report,
	)
	if frames != 1 || report.DataErrors != 1 || report.DroppedData {
		t.Fatalf("frames=%d report=%+v", frames, report)
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

// A displayed length is one hex digit. Accepting two swallowed any first data byte
// that read as a small decimal, shifting every offset in the frame by one — and
// only for the frames whose first byte happened to look like that.
func TestFirstDataByteIsNotMistakenForALength(t *testing.T) {
	frame, err := ParseCANFrame("374 00 96 00 00 00 00 00 00", 1)
	if err != nil {
		t.Fatal(err)
	}
	if len(frame.Data) != 8 || frame.Data[0] != 0x00 || frame.Data[1] != 0x96 {
		t.Fatalf("data=% X, want the leading 00 kept as data", frame.Data)
	}

	// A genuine displayed length is still recognised.
	withLength, err := ParseCANFrame("374 8 00 96 00 00 00 00 00 00", 1)
	if err != nil {
		t.Fatal(err)
	}
	if len(withLength.Data) != 8 || withLength.Data[1] != 0x96 {
		t.Fatalf("data=% X, want the length consumed and the data kept", withLength.Data)
	}
}

// A vehicle bus runs at 500 kbit/s and the serial link carries 115200, so an
// unfiltered monitor asks for roughly four times what the cable can take.
func TestPassFiltersAskForOnlyTheProfilesIdentifiers(t *testing.T) {
	port := &recordingPort{scriptedPort: scriptedPort{replies: map[string]string{"STFAP": "OK\r>"}}}
	adapter := NewOBDAdapter("scripted")
	adapter.port = port
	adapter.CommandWindow = time.Second

	if err := adapter.PassFilters([]int{0x101, 0x373, 0x374}); err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{"STFAP 101,FFF", "STFAP 373,FFF", "STFAP 374,FFF"} {
		if !strings.Contains(port.written, want) {
			t.Fatalf("wrote %q, missing %q", port.written, want)
		}
	}

	// A 29-bit identifier has no three-digit form, so it is refused rather than
	// silently truncated into a filter that would pass the wrong traffic.
	if err := adapter.PassFilters([]int{0x1FFFFFFF}); err == nil {
		t.Fatal("expected an extended identifier to be refused")
	}
}

func TestMonitorCommandsKeepRuntimeFilteredAndDiagnosticsUnfiltered(t *testing.T) {
	for _, test := range []struct {
		name    string
		prepare func(*OBDAdapter) error
		monitor func(*OBDAdapter) error
		want    string
	}{
		{
			name: "profile runtime",
			prepare: func(adapter *OBDAdapter) error {
				return adapter.PassFilters([]int{0x101, 0x373})
			},
			monitor: func(adapter *OBDAdapter) error {
				return adapter.Monitor(20*time.Millisecond, func(model.CANFrame) {})
			},
			want: "STFAP 101,FFF\rSTFAP 373,FFF\rATCAF0\rSTM\r\r",
		},
		{
			name: "unfiltered diagnostics",
			monitor: func(adapter *OBDAdapter) error {
				_, err := adapter.MonitorAllReport(20*time.Millisecond, func(model.CANFrame) {})
				return err
			},
			want: "ATCAF0\rSTMA\r\r",
		},
	} {
		t.Run(test.name, func(t *testing.T) {
			port := &recordingPort{scriptedPort: scriptedPort{replies: map[string]string{
				"ATCAF0": "OK\r>",
				"STFAP":  "OK\r>",
				"STM":    "374 8 96 00 00 00 00 00 00 00\r",
				"\r":     "STOPPED\r>",
			}}}
			adapter := NewOBDAdapter("scripted")
			adapter.port = port
			adapter.CommandWindow = time.Second

			if test.prepare != nil {
				if err := test.prepare(adapter); err != nil {
					t.Fatal(err)
				}
			}
			if err := test.monitor(adapter); err != nil {
				t.Fatal(err)
			}
			if port.written != test.want {
				t.Fatalf("wrote %q, want %q", port.written, test.want)
			}
		})
	}
}

func TestHighSpeedNegotiationFallsBackAndRestoresDefaultOnClose(t *testing.T) {
	port := &baudPort{current: defaultOBDBaudRate, supported: map[int]bool{
		1000000: true, defaultOBDBaudRate: true,
	}}
	adapter := NewOBDAdapter("scripted")
	adapter.port = port
	adapter.BaudSwitchWindow = 5 * time.Millisecond

	adapter.negotiateHighSpeed()
	if adapter.BaudRate() != 1000000 {
		t.Fatalf("baud=%d, want the highest supported fallback", adapter.BaudRate())
	}
	adapter.Close()

	wantWrites := "STBRT 500\rSTBR 2000000\rSTI\rSTBRT 500\rSTBR 1000000\r\rSTI\rSTI\rSTI\rSTBRT 500\rSTBR 115200\r\r"
	if port.written != wantWrites {
		t.Fatalf("wrote %q, want %q", port.written, wantWrites)
	}
	wantModes := []int{2000000, defaultOBDBaudRate, 1000000, defaultOBDBaudRate}
	if len(port.modes) != len(wantModes) {
		t.Fatalf("baud modes=%v, want %v", port.modes, wantModes)
	}
	for index, want := range wantModes {
		if port.modes[index] != want {
			t.Fatalf("baud modes=%v, want %v", port.modes, wantModes)
		}
	}
}

func TestHighSpeedNegotiationLeavesNonSTNAdapterAtDefault(t *testing.T) {
	port := &scriptedPort{replies: map[string]string{"STBRT": "?\r>"}}
	adapter := NewOBDAdapter("scripted")
	adapter.port = port
	adapter.negotiateHighSpeed()
	if adapter.BaudRate() != defaultOBDBaudRate {
		t.Fatalf("baud=%d, want default", adapter.BaudRate())
	}
}

func TestHighSpeedNegotiationVerifiesANewRateWhenTheFinalOKIsLost(t *testing.T) {
	port := &baudPort{
		current: defaultOBDBaudRate,
		supported: map[int]bool{
			2000000: true, defaultOBDBaudRate: true,
		},
		dropFinalOK: true,
	}
	adapter := NewOBDAdapter("scripted")
	adapter.port = port
	adapter.BaudSwitchWindow = 5 * time.Millisecond

	adapter.negotiateHighSpeed()
	if adapter.BaudRate() != 2000000 {
		t.Fatalf("baud=%d, want verified 2000000", adapter.BaudRate())
	}
	if port.written != "STBRT 500\rSTBR 2000000\r\rSTI\rSTI\rSTI\rSTI\r" {
		t.Fatalf("wrote %q", port.written)
	}
}

func TestHighSpeedNegotiationReturnsToDefaultWhenTrafficIsNotSustained(t *testing.T) {
	port := &baudPort{
		current: defaultOBDBaudRate,
		supported: map[int]bool{
			2000000: true, defaultOBDBaudRate: true,
		},
		failSTIAfter: 1,
	}
	adapter := NewOBDAdapter("scripted")
	adapter.port = port
	adapter.BaudSwitchWindow = 5 * time.Millisecond

	adapter.negotiateHighSpeed()
	if adapter.BaudRate() != defaultOBDBaudRate {
		t.Fatalf("baud=%d, want the verified default after high-speed traffic failed", adapter.BaudRate())
	}
	if len(port.modes) < 2 || port.modes[0] != 2000000 || port.modes[len(port.modes)-1] != defaultOBDBaudRate {
		t.Fatalf("baud modes=%v, want high-speed trial followed by default", port.modes)
	}
}

func TestMonitorKeepsFlaggedFramesInCensusAndReportsDroppedData(t *testing.T) {
	port := &scriptedPort{replies: map[string]string{
		"ATCAF0": "OK\r>",
		"STMA": "374 8F 90 9D FE 4F 4B 47 14 <DATA ERROR\r" +
			"373 BB BB 7F 4E 0C 65 00 16 <DATA ERROR\r" +
			"412 FE 00 01 19 7A 00 21 12 <DATA ERROR\r" +
			"298 43 42 4A 42 43 00 27 10 <DATA ERROR\r389 8 01 02\r<RX ERROR\r",
		"\r": "BUFFER FULL\rSTOPPED\r>",
	}}
	adapter := NewOBDAdapter("scripted")
	adapter.port = port
	adapter.CommandWindow = time.Second
	seen := map[int]int{}
	report, err := adapter.MonitorAllReport(20*time.Millisecond, func(frame model.CANFrame) { seen[frame.CANID]++ })
	if err != nil {
		t.Fatal(err)
	}
	for _, canID := range []int{0x374, 0x373, 0x412, 0x298} {
		if seen[canID] != 1 {
			t.Fatalf("census=%v, missing flagged identifier %03X", seen, canID)
		}
	}
	if !report.BufferFull || report.DataErrors != 4 || report.AdapterErrors != 1 || report.MalformedFrames != 1 || !report.DroppedData {
		t.Fatalf("census=%v report=%+v", seen, report)
	}
}

func TestWatchCANIDSetsOneHardwareReceiveFilter(t *testing.T) {
	port := &recordingPort{scriptedPort: scriptedPort{replies: map[string]string{"ATCRA": "OK\r>"}}}
	adapter := NewOBDAdapter("scripted")
	adapter.port = port
	if err := adapter.WatchCANID(0x373); err != nil {
		t.Fatal(err)
	}
	if port.written != "ATCRA 373\r" {
		t.Fatalf("wrote %q", port.written)
	}
}

type baudPort struct {
	scriptedPort
	written      string
	current      int
	requested    int
	supported    map[int]bool
	modes        []int
	dropFinalOK  bool
	stiCount     int
	failSTIAfter int
}

func (port *baudPort) Write(payload []byte) (int, error) {
	command := string(payload)
	port.written += command
	switch {
	case strings.HasPrefix(command, "STBRT"):
		port.pending = "OK\r>"
	case strings.HasPrefix(command, "STBR "):
		port.requested, _ = strconv.Atoi(strings.TrimSpace(strings.TrimPrefix(command, "STBR ")))
		port.pending = ""
	case command == "\r" && port.current == port.requested && port.supported[port.current]:
		if port.dropFinalOK {
			port.dropFinalOK = false
			port.pending = ""
		} else {
			port.pending = "OK\r>"
		}
		port.requested = 0
	case command == "STI\r" && port.supported[port.current]:
		port.stiCount++
		if port.failSTIAfter == 0 || port.stiCount <= port.failSTIAfter {
			port.pending = "STN1130 v4.0.1\r>"
		} else {
			port.pending = ""
		}
	}
	return len(payload), nil
}

func (port *baudPort) SetMode(mode *serial.Mode) error {
	port.current = mode.BaudRate
	port.modes = append(port.modes, mode.BaudRate)
	if port.current == port.requested && port.supported[port.current] {
		port.pending = "STN1130 v4.0.1\r"
	}
	return nil
}

type recordingPort struct {
	scriptedPort
	written string
}

func (port *recordingPort) Write(payload []byte) (int, error) {
	port.written += string(payload)
	return port.scriptedPort.Write(payload)
}
