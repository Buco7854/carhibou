package providers

import (
	"encoding/hex"
	"fmt"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/Buco7854/carhibou/agent/internal/model"
	"go.bug.st/serial"
)

var compactFrame = regexp.MustCompile(`^([0-9A-Fa-f]{3}|[0-9A-Fa-f]{8})([0-9A-Fa-f]+)$`)

// obdReadPoll is how long one read waits before the deadline is re-checked, and
// obdCommandWindow is the longest an adapter may take to answer a command.
const (
	obdReadPoll        = 200 * time.Millisecond
	obdCommandWindow   = 5 * time.Second
	defaultOBDBaudRate = 115200
	baudSwitchTimeout  = 500 * time.Millisecond
)

var highSpeedBaudRates = []int{2000000, 1000000, 921600, 500000, 460800, 230400}

type OBDAdapter struct {
	device string
	port   serial.Port
	buffer []byte
	// pending holds bytes read past the end of the previous reply, because a
	// serial read returns whatever has arrived rather than one whole response.
	pending string
	// CommandWindow bounds how long one command may wait for its reply.
	CommandWindow    time.Duration
	BaudSwitchWindow time.Duration
	baudRate         int
}

func NewOBDAdapter(device string) *OBDAdapter {
	return &OBDAdapter{
		device: device, buffer: make([]byte, 512), CommandWindow: obdCommandWindow,
		BaudSwitchWindow: baudSwitchTimeout, baudRate: defaultOBDBaudRate,
	}
}

func (adapter *OBDAdapter) Connect() error {
	adapter.Close()
	port, err := serial.Open(adapter.device, &serial.Mode{BaudRate: defaultOBDBaudRate})
	if err != nil {
		return err
	}
	if err := port.SetReadTimeout(obdReadPoll); err != nil {
		port.Close()
		return err
	}
	adapter.port = port
	for _, command := range []string{"ATZ", "ATE0", "ATL0", "ATS1", "ATH1"} {
		delay := time.Duration(0)
		if command == "ATZ" {
			delay = time.Second
		}
		if _, err := adapter.Command(command, delay); err != nil {
			adapter.Close()
			return err
		}
	}
	adapter.negotiateHighSpeed()
	return nil
}

func (adapter *OBDAdapter) Close() {
	if adapter.port != nil {
		adapter.restoreDefaultBaud()
		adapter.port.Close()
	}
	adapter.port = nil
	adapter.pending = ""
	adapter.baudRate = defaultOBDBaudRate
}

func (adapter *OBDAdapter) BaudRate() int { return adapter.baudRate }

func (adapter *OBDAdapter) negotiateHighSpeed() {
	if _, err := adapter.Command(fmt.Sprintf("STBRT %d", baudSwitchTimeout.Milliseconds()), 0); err != nil {
		return
	}
	for _, baudRate := range highSpeedBaudRates {
		if adapter.switchBaud(baudRate) == nil {
			return
		}
	}
}

func (adapter *OBDAdapter) switchBaud(baudRate int) error {
	previous := adapter.baudRate
	if err := adapter.port.ResetInputBuffer(); err != nil {
		return err
	}
	adapter.pending = ""
	if _, err := adapter.port.Write([]byte(fmt.Sprintf("STBR %d\r", baudRate))); err != nil {
		return err
	}
	if err := adapter.port.Drain(); err != nil {
		return err
	}
	if err := adapter.port.SetMode(&serial.Mode{BaudRate: baudRate}); err != nil {
		adapter.recoverBaud(previous)
		return err
	}
	identity, err := adapter.readUntil('\r', adapter.BaudSwitchWindow)
	if err != nil || !strings.HasPrefix(strings.ToUpper(strings.TrimSpace(identity)), "STN") {
		adapter.recoverBaud(previous)
		return fmt.Errorf("adapter did not confirm %d baud", baudRate)
	}
	if _, err := adapter.port.Write([]byte("\r")); err != nil {
		adapter.recoverBaud(previous)
		return err
	}
	if err := adapter.port.Drain(); err != nil {
		adapter.recoverBaud(previous)
		return err
	}
	response, err := adapter.readUntil('>', adapter.BaudSwitchWindow)
	if err != nil || !responseContains(response, "OK") {
		if adapter.probeBaud() {
			adapter.baudRate = baudRate
			return nil
		}
		adapter.recoverBaud(previous)
		return fmt.Errorf("adapter did not accept %d baud", baudRate)
	}
	adapter.baudRate = baudRate
	return nil
}

func (adapter *OBDAdapter) probeBaud() bool {
	_ = adapter.port.ResetInputBuffer()
	adapter.pending = ""
	if _, err := adapter.port.Write([]byte("STI\r")); err != nil {
		return false
	}
	if err := adapter.port.Drain(); err != nil {
		return false
	}
	response, err := adapter.readUntil('>', adapter.BaudSwitchWindow)
	return err == nil && strings.Contains(strings.ToUpper(response), "STN")
}

func responseContains(response, expected string) bool {
	for _, line := range strings.FieldsFunc(response, func(r rune) bool { return r == '\r' || r == '\n' }) {
		if strings.EqualFold(strings.TrimSpace(line), expected) {
			return true
		}
	}
	return false
}

func (adapter *OBDAdapter) recoverBaud(baudRate int) {
	time.Sleep(adapter.BaudSwitchWindow + obdReadPoll)
	_ = adapter.port.SetMode(&serial.Mode{BaudRate: baudRate})
	_ = adapter.port.ResetInputBuffer()
	adapter.pending = ""
}

func (adapter *OBDAdapter) restoreDefaultBaud() {
	if adapter.baudRate == defaultOBDBaudRate {
		return
	}
	current := adapter.baudRate
	if adapter.switchBaud(defaultOBDBaudRate) == nil {
		return
	}
	_ = adapter.port.SetMode(&serial.Mode{BaudRate: current})
	_, _ = adapter.port.Write([]byte("ATZ\r"))
	_ = adapter.port.Drain()
	time.Sleep(time.Second)
	_ = adapter.port.SetMode(&serial.Mode{BaudRate: defaultOBDBaudRate})
}

// readUntil collects bytes until the terminator arrives or the window closes.
//
// A serial read timeout surfaces as a zero-length read with a nil error, which a
// bufio.Reader counts as progress and retries a hundred times before reporting
// one. A silent adapter therefore stalled for a hundred read timeouts per command
// instead of the one it was configured for, so the window is enforced here.
func (adapter *OBDAdapter) readUntil(terminator byte, window time.Duration) (string, error) {
	deadline := time.Now().Add(window)
	for {
		if index := strings.IndexByte(adapter.pending, terminator); index >= 0 {
			response := adapter.pending[:index]
			adapter.pending = adapter.pending[index+1:]
			return response, nil
		}
		if !time.Now().Before(deadline) {
			return "", fmt.Errorf("adapter did not answer within %s", window)
		}
		count, err := adapter.port.Read(adapter.buffer)
		if count > 0 {
			adapter.pending += string(adapter.buffer[:count])
			if len(adapter.pending) > maxPending {
				adapter.pending = adapter.pending[len(adapter.pending)-maxPending:]
			}
		}
		if err != nil {
			return "", err
		}
	}
}

func (adapter *OBDAdapter) Command(command string, delay time.Duration) ([]string, error) {
	if adapter.port == nil {
		return nil, fmt.Errorf("adapter is not connected")
	}
	if err := adapter.port.ResetInputBuffer(); err != nil {
		return nil, err
	}
	// Bytes buffered from an earlier reply would otherwise be read as this one.
	adapter.pending = ""
	if _, err := adapter.port.Write([]byte(strings.TrimSpace(command) + "\r")); err != nil {
		return nil, err
	}
	if delay > 0 {
		time.Sleep(delay)
	}
	response, err := adapter.readUntil('>', adapter.CommandWindow)
	if err != nil {
		return nil, fmt.Errorf("%s: %w", command, err)
	}
	lines := []string{}
	for _, line := range strings.FieldsFunc(response, func(r rune) bool { return r == '\r' || r == '\n' }) {
		line = strings.TrimSpace(line)
		if line != "" && !strings.EqualFold(line, command) {
			lines = append(lines, line)
		}
	}
	if len(lines) == 0 {
		return nil, fmt.Errorf("adapter returned no response to %s", command)
	}
	for _, line := range lines {
		if line == "?" || line == "ERROR" || line == "UNABLE TO CONNECT" {
			return nil, fmt.Errorf("adapter rejected %s: %v", command, lines)
		}
	}
	return lines, nil
}

// VehicleAnswered reports whether a reply came from the vehicle rather than from
// the adapter saying that nothing did.
//
// An adapter with no vehicle behind it still answers, which is why a null VIN and
// an empty fault list look the same whether the car is asleep or the reading
// failed. "NO DATA" and a protocol search that found nothing are the adapter
// speaking for itself.
func VehicleAnswered(lines []string) bool {
	for _, line := range lines {
		upper := strings.ToUpper(strings.TrimSpace(line))
		if upper == "" || upper == "NO DATA" || upper == "STOPPED" || upper == "ERROR" || upper == "?" {
			continue
		}
		if strings.HasPrefix(upper, "SEARCHING") || strings.Contains(upper, "UNABLE TO CONNECT") {
			continue
		}
		return true
	}
	return false
}

// Voltage reads the supply at the adapter's connector.
//
// It comes from the adapter, not the vehicle, so it answers with the ignition off
// and is the one measurement that distinguishes an agent plugged into a car from
// one plugged into nothing. Around 12.4 V is a resting battery; 13.5 V or more
// means something is charging it.
func (adapter *OBDAdapter) Voltage() (string, error) {
	lines, err := adapter.Command("ATRV", 0)
	if err != nil {
		return "", err
	}
	if len(lines) == 0 {
		return "", fmt.Errorf("adapter reported no voltage")
	}
	return strings.TrimSpace(lines[0]), nil
}

// Protocol describes the link the adapter has settled on with the vehicle.
func (adapter *OBDAdapter) Protocol() (string, error) {
	lines, err := adapter.Command("ATDP", 0)
	if err != nil {
		return "", err
	}
	if len(lines) == 0 {
		return "", fmt.Errorf("adapter reported no protocol")
	}
	return strings.TrimSpace(lines[0]), nil
}

func (adapter *OBDAdapter) Identity() (map[string]string, error) {
	identity, err := adapter.Command("ATI", 0)
	if err != nil {
		return nil, err
	}
	firmware, err := adapter.Command("STI", 0)
	if err != nil {
		return nil, err
	}
	return map[string]string{"adapter": strings.Join(identity, " "), "firmware": strings.Join(firmware, " ")}, nil
}

func (adapter *OBDAdapter) SelectProtocol(protocol string) error {
	if matched, _ := regexp.MatchString(`^[0-9A-Ca-c]$`, protocol); !matched {
		return fmt.Errorf("invalid ELM protocol identifier")
	}
	_, err := adapter.Command("ATSP"+strings.ToUpper(protocol), 0)
	return err
}

func (adapter *OBDAdapter) Query(mode, pid int) ([]string, error) {
	return adapter.Command(fmt.Sprintf("%02X%02X", mode, pid), 0)
}

// PassFilters restricts monitoring to the given CAN identifiers.
//
// Without them a monitor sees every frame on the bus. ASCII expansion can overrun
// even a faster UART on a busy CAN bus, so filtering happens in the adapter.
//
// A reset clears filters, and Connect resets, so there is nothing to clear first.
func (adapter *OBDAdapter) PassFilters(canIDs []int) error {
	for _, canID := range canIDs {
		if canID < 0 || canID > 0x7FF {
			// Only 11-bit identifiers have the three-digit form this takes.
			return fmt.Errorf("cannot filter on identifier %#x", canID)
		}
		if _, err := adapter.Command(fmt.Sprintf("STFAP %03X,FFF", canID), 0); err != nil {
			return err
		}
	}
	return nil
}

func (adapter *OBDAdapter) WatchCANID(canID int) error {
	if canID < 0 || canID > 0x1FFFFFFF {
		return fmt.Errorf("CAN identifier %#x is outside 29-bit bounds", canID)
	}
	width := 3
	if canID > 0x7FF {
		width = 8
	}
	_, err := adapter.Command(fmt.Sprintf("ATCRA %0*X", width, canID), 0)
	return err
}

type MonitorReport struct {
	BufferFull      bool `json:"buffer_full"`
	DataErrors      int  `json:"data_errors"`
	AdapterErrors   int  `json:"adapter_errors"`
	MalformedFrames int  `json:"malformed_frames"`
	DroppedData     bool `json:"dropped_data"`
}

// Monitor streams filtered frames for a fixed period. Sampling uses MonitorUntil
// because a fixed window cannot be part of a loop that samples every second.
func (adapter *OBDAdapter) Monitor(duration time.Duration, onFrame func(model.CANFrame)) error {
	_, err := adapter.MonitorReport(duration, onFrame)
	return err
}

func (adapter *OBDAdapter) MonitorReport(duration time.Duration, onFrame func(model.CANFrame)) (MonitorReport, error) {
	stop := make(chan struct{})
	timer := time.AfterFunc(duration, func() { close(stop) })
	defer timer.Stop()
	return adapter.monitorUntil(stop, "STM", onFrame)
}

func (adapter *OBDAdapter) MonitorAllReport(duration time.Duration, onFrame func(model.CANFrame)) (MonitorReport, error) {
	stop := make(chan struct{})
	timer := time.AfterFunc(duration, func() { close(stop) })
	defer timer.Stop()
	return adapter.monitorUntil(stop, "STMA", onFrame)
}

// MonitorUntil streams frames until stop is closed.
//
// Monitoring is continuous on the wire whether or not anyone is reading, so a
// sampling loop that opened a window per sample saw only the fraction of the bus
// that fell inside its windows, and blocked for the whole of each one. Running it
// once for the life of the connection means a sample is a snapshot of values kept
// current in the background, which costs nothing per sample and misses nothing
// between them.
func (adapter *OBDAdapter) MonitorUntil(stop <-chan struct{}, onFrame func(model.CANFrame)) error {
	_, err := adapter.monitorUntil(stop, "STM", onFrame)
	return err
}

func (adapter *OBDAdapter) monitorUntil(
	stop <-chan struct{}, command string, onFrame func(model.CANFrame),
) (MonitorReport, error) {
	report := MonitorReport{}
	if adapter.port == nil {
		return report, fmt.Errorf("adapter is not connected")
	}
	// Broadcast payloads are raw CAN, not ISO 15765 messages for CAF to validate.
	if _, err := adapter.Command("ATCAF0", 0); err != nil {
		return report, err
	}
	if err := adapter.port.ResetInputBuffer(); err != nil {
		return report, err
	}
	adapter.pending = ""
	if _, err := adapter.port.Write([]byte(command + "\r")); err != nil {
		return report, err
	}
	for {
		select {
		case <-stop:
			_, err := adapter.port.Write([]byte("\r"))
			if err == nil {
				var response string
				response, err = adapter.readUntil('>', adapter.CommandWindow)
				for _, line := range strings.FieldsFunc(response, func(r rune) bool { return r == '\r' || r == '\n' }) {
					observeMonitorLine(strings.TrimSpace(line), onFrame, &report)
				}
			}
			return report, err
		default:
		}
		// A short read window keeps the stop signal responsive on a quiet bus
		// without spinning: the read itself is what waits.
		line, err := adapter.readUntil('\r', monitorReadWindow)
		if err != nil {
			continue
		}
		observeMonitorLine(strings.TrimSpace(line), onFrame, &report)
	}
}

func observeMonitorLine(line string, onFrame func(model.CANFrame), report *MonitorReport) {
	if line == "" || line == "SEARCHING..." {
		return
	}
	upper := strings.ToUpper(line)
	if strings.Contains(upper, "BUFFER FULL") {
		report.BufferFull = true
		report.DroppedData = true
		return
	}
	if marker := strings.Index(upper, "<DATA ERROR"); marker >= 0 {
		report.DataErrors++
		line = strings.TrimSpace(line[:marker])
		upper = strings.ToUpper(line)
	}
	if strings.Contains(upper, "DATA ERROR") {
		report.DataErrors++
		report.DroppedData = true
		return
	}
	if strings.Contains(upper, "CAN ERROR") || strings.Contains(upper, "RX ERROR") {
		report.AdapterErrors++
		report.DroppedData = true
		return
	}
	frame, err := ParseCANFrame(line, float64(time.Now().UnixNano())/1e9)
	if err == nil {
		onFrame(frame)
	} else if upper != "STOPPED" {
		report.MalformedFrames++
		report.DroppedData = true
	}
}

// monitorReadWindow bounds one read so a stopped monitor does not wait out a
// silent bus before noticing.
const monitorReadWindow = 300 * time.Millisecond

func ParseCANFrame(line string, timestamp float64) (model.CANFrame, error) {
	if marker := strings.Index(strings.ToUpper(line), "<DATA ERROR"); marker >= 0 {
		line = line[:marker]
	}
	cleaned := strings.TrimSpace(strings.ReplaceAll(line, ":", " "))
	parts := strings.Fields(cleaned)
	var canIDText, dataText string
	declared := -1
	if len(parts) < 2 {
		matches := compactFrame.FindStringSubmatch(cleaned)
		if matches == nil {
			return model.CANFrame{}, fmt.Errorf("unrecognized CAN frame %q", line)
		}
		canIDText, dataText = matches[1], matches[2]
	} else {
		canIDText = parts[0]
		remaining := parts[1:]
		// A displayed length is one hex digit. Accepting two swallowed any first
		// data byte that happened to read as a small decimal — "00" through "08" —
		// shifting every offset in the frame by one, but only for some frames.
		if value, err := strconv.Atoi(remaining[0]); err == nil && len(remaining[0]) == 1 && value <= 8 {
			declared = value
			remaining = remaining[1:]
		}
		dataText = strings.Join(remaining, "")
	}
	payload, err := hex.DecodeString(dataText)
	if err != nil {
		return model.CANFrame{}, err
	}
	if declared >= 0 && declared != len(payload) {
		return model.CANFrame{}, fmt.Errorf("CAN data length does not match declared DLC")
	}
	canID, err := strconv.ParseInt(canIDText, 16, 32)
	if err != nil || canID < 0 || canID > 0x1fffffff || len(payload) > 8 {
		return model.CANFrame{}, fmt.Errorf("CAN identifier or payload is outside classic CAN bounds")
	}
	return model.CANFrame{Timestamp: timestamp, CANID: int(canID), Data: payload}, nil
}

type PIDDefinition struct {
	Name   string
	Unit   string
	Decode func([]byte) (float64, error)
}

var StandardPIDs = map[int]PIDDefinition{
	0x04: {"engine.load", "%", func(data []byte) (float64, error) { value, err := byteA(data); return value * 100 / 255, err }},
	0x05: {"engine.coolant_temperature", "°C", func(data []byte) (float64, error) { value, err := byteA(data); return value - 40, err }},
	0x0C: {"engine.rpm", "rpm", func(data []byte) (float64, error) { value, err := bytesAB(data); return value / 4, err }},
	0x0D: {"vehicle.speed", "km/h", byteA},
	0x0F: {"engine.intake_temperature", "°C", func(data []byte) (float64, error) { value, err := byteA(data); return value - 40, err }},
	0x10: {"engine.maf", "g/s", func(data []byte) (float64, error) { value, err := bytesAB(data); return value / 100, err }},
	0x11: {"engine.throttle", "%", func(data []byte) (float64, error) { value, err := byteA(data); return value * 100 / 255, err }},
	0x2F: {"fuel.level", "%", func(data []byte) (float64, error) { value, err := byteA(data); return value * 100 / 255, err }},
	0x42: {"agent.input_voltage", "V", func(data []byte) (float64, error) { value, err := bytesAB(data); return value / 1000, err }},
	// Mode 01 PID 5B is the only standard route to hybrid/EV pack charge. SAE J1979 names
	// it "hybrid battery pack remaining life" and scan tools read it as pack charge, but
	// few vehicles answer it and the reading is unverified against a car. A vehicle
	// profile remains the accurate source when one exists; a car that does not support
	// the PID simply returns no data and nothing is published.
	0x5B: {"battery.soc", "%", func(data []byte) (float64, error) { value, err := byteA(data); return value * 100 / 255, err }},
}

func ParseOBDResponse(mode, pid int, lines []string) []byte {
	expected := []byte{byte(mode + 0x40), byte(pid)}
	for _, line := range lines {
		parts := strings.Fields(strings.ReplaceAll(line, ":", " "))
		if len(parts) > 0 && (len(parts[0]) == 3 || len(parts[0]) == 8) {
			parts = parts[1:]
		}
		if len(parts) > 0 && len(parts[0]) == 2 {
			if value, err := strconv.ParseInt(parts[0], 16, 8); err == nil && value <= 8 {
				parts = parts[1:]
			}
		}
		raw, err := hex.DecodeString(strings.Join(parts, ""))
		if err != nil {
			continue
		}
		for offset := 0; offset+1 < len(raw); offset++ {
			if raw[offset] == expected[0] && raw[offset+1] == expected[1] {
				return raw[offset+2:]
			}
		}
	}
	return nil
}

func ParseVIN(lines []string) string {
	payload := []byte{}
	for _, line := range lines {
		raw := linePayload(line)
		if len(raw) == 0 {
			continue
		}
		var chunk []byte
		switch raw[0] >> 4 {
		case 1:
			if len(raw) > 2 {
				chunk = raw[2:]
			}
		case 2:
			chunk = raw[1:]
		default:
			if raw[0] <= 8 {
				chunk = raw[1:]
			} else {
				chunk = raw
			}
		}
		marker := -1
		for index := 0; index+1 < len(chunk); index++ {
			if chunk[index] == 0x49 && chunk[index+1] == 0x02 {
				marker = index
				break
			}
		}
		if marker >= 0 {
			chunk = chunk[marker+2:]
			if len(chunk) > 0 && chunk[0] >= 1 && chunk[0] <= 3 {
				chunk = chunk[1:]
			}
		}
		for _, value := range chunk {
			if value >= 32 && value <= 126 {
				payload = append(payload, value)
			}
		}
	}
	if len(payload) < 17 {
		return ""
	}
	return string(payload[:17])
}

func ParseDTC(lines []string) []string {
	codes := []string{}
	families := "PCBU"
	for _, line := range lines {
		raw := linePayload(line)
		marker := -1
		for index, value := range raw {
			if value == 0x43 {
				marker = index
				break
			}
		}
		if marker < 0 {
			continue
		}
		data := raw[marker+1:]
		for offset := 0; offset+1 < len(data); offset += 2 {
			first, second := data[offset], data[offset+1]
			if first == 0 && second == 0 {
				continue
			}
			codes = append(codes, fmt.Sprintf("%c%X%X%02X", families[first>>6], (first>>4)&3, first&15, second))
		}
	}
	return codes
}

func linePayload(line string) []byte {
	parts := strings.Fields(strings.ReplaceAll(line, ":", " "))
	if len(parts) > 0 && (len(parts[0]) == 3 || len(parts[0]) == 8) {
		parts = parts[1:]
	}
	result, _ := hex.DecodeString(strings.Join(parts, ""))
	return result
}

func byteA(data []byte) (float64, error) {
	if len(data) == 0 {
		return 0, fmt.Errorf("OBD response has no data bytes")
	}
	return float64(data[0]), nil
}
func bytesAB(data []byte) (float64, error) {
	if len(data) < 2 {
		return 0, fmt.Errorf("OBD response requires two data bytes")
	}
	return float64(int(data[0])*256 + int(data[1])), nil
}

type StandardOBDProvider struct {
	adapter   *OBDAdapter
	connected bool
	failure   string
	nextTry   time.Time
}

func NewStandardOBDProvider(adapter *OBDAdapter) *StandardOBDProvider {
	return &StandardOBDProvider{adapter: adapter}
}

// Status explains why the provider is publishing nothing. See ProfileProvider.
func (provider *StandardOBDProvider) Status() string { return provider.failure }

func (provider *StandardOBDProvider) Live() bool {
	return provider.connected && provider.failure == ""
}

func (provider *StandardOBDProvider) ReadObservations() (model.MetricObservations, error) {
	if !provider.connected {
		if time.Now().Before(provider.nextTry) {
			return model.MetricObservations{}, nil
		}
		provider.nextTry = time.Now().Add(connectRetryInterval)
		if err := provider.adapter.Connect(); err != nil {
			provider.failure = "adapter did not connect: " + err.Error()
			return model.MetricObservations{}, nil
		}
		if err := provider.adapter.SelectProtocol("0"); err != nil {
			provider.adapter.Close()
			provider.failure = "adapter rejected automatic protocol search: " + err.Error()
			return model.MetricObservations{}, nil
		}
		provider.connected = true
		provider.failure = ""
	}
	observations := model.MetricObservations{}
	for pid, definition := range StandardPIDs {
		lines, err := provider.adapter.Query(1, pid)
		if err != nil {
			provider.adapter.Close()
			provider.connected = false
			provider.failure = "adapter stopped answering: " + err.Error()
			return observations, nil
		}
		data := ParseOBDResponse(1, pid, lines)
		if data == nil {
			continue
		}
		value, err := definition.Decode(data)
		if err == nil {
			observations[definition.Name] = model.MetricObservation{
				Value: value,
				Metadata: model.ObservationMetadata{
					ObservedAt: time.Now().UTC(),
					Channel:    model.ChannelOBD,
					Method:     model.MethodDirect,
				},
			}
		}
	}
	return observations, nil
}
func (provider *StandardOBDProvider) Close() { provider.adapter.Close() }
