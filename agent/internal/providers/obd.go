package providers

import (
	"bufio"
	"encoding/hex"
	"fmt"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/Buco7854/vehinode/agent/internal/model"
	"go.bug.st/serial"
)

var compactFrame = regexp.MustCompile(`^([0-9A-Fa-f]{3}|[0-9A-Fa-f]{8})([0-9A-Fa-f]+)$`)

type OBDAdapter struct {
	device string
	port   serial.Port
	reader *bufio.Reader
}

func NewOBDAdapter(device string) *OBDAdapter { return &OBDAdapter{device: device} }

func (adapter *OBDAdapter) Connect() error {
	adapter.Close()
	port, err := serial.Open(adapter.device, &serial.Mode{BaudRate: 115200})
	if err != nil {
		return err
	}
	if err := port.SetReadTimeout(2 * time.Second); err != nil {
		port.Close()
		return err
	}
	adapter.port = port
	adapter.reader = bufio.NewReader(port)
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
	return nil
}

func (adapter *OBDAdapter) Close() {
	if adapter.port != nil {
		adapter.port.Close()
	}
	adapter.port = nil
	adapter.reader = nil
}

func (adapter *OBDAdapter) Command(command string, delay time.Duration) ([]string, error) {
	if adapter.port == nil {
		return nil, fmt.Errorf("adapter is not connected")
	}
	if err := adapter.port.ResetInputBuffer(); err != nil {
		return nil, err
	}
	if _, err := adapter.port.Write([]byte(strings.TrimSpace(command) + "\r")); err != nil {
		return nil, err
	}
	if delay > 0 {
		time.Sleep(delay)
	}
	response, err := adapter.reader.ReadString('>')
	if err != nil {
		return nil, err
	}
	lines := []string{}
	for _, line := range strings.FieldsFunc(strings.ReplaceAll(response, ">", ""), func(r rune) bool { return r == '\r' || r == '\n' }) {
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

func (adapter *OBDAdapter) Monitor(duration time.Duration, onFrame func(model.CANFrame)) error {
	if adapter.port == nil {
		return fmt.Errorf("adapter is not connected")
	}
	if err := adapter.port.ResetInputBuffer(); err != nil {
		return err
	}
	if _, err := adapter.port.Write([]byte("STM\r")); err != nil {
		return err
	}
	deadline := time.Now().Add(duration)
	for time.Now().Before(deadline) {
		line, err := adapter.reader.ReadString('\r')
		if err != nil {
			continue
		}
		line = strings.TrimSpace(line)
		if line == "" || line == "SEARCHING..." {
			continue
		}
		frame, err := ParseCANFrame(line, float64(time.Now().UnixNano())/1e9)
		if err == nil {
			onFrame(frame)
		}
	}
	_, err := adapter.port.Write([]byte("\r"))
	if err == nil {
		_, err = adapter.reader.ReadString('>')
	}
	return err
}

func ParseCANFrame(line string, timestamp float64) (model.CANFrame, error) {
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
		if value, err := strconv.Atoi(remaining[0]); err == nil && value <= 8 {
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
	0x42: {"device.input_voltage", "V", func(data []byte) (float64, error) { value, err := bytesAB(data); return value / 1000, err }},
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
}

func NewStandardOBDProvider(adapter *OBDAdapter) *StandardOBDProvider {
	return &StandardOBDProvider{adapter: adapter}
}
func (provider *StandardOBDProvider) ReadMetrics() (map[string]any, error) {
	if !provider.connected {
		if err := provider.adapter.Connect(); err != nil {
			return map[string]any{}, nil
		}
		if err := provider.adapter.SelectProtocol("0"); err != nil {
			provider.adapter.Close()
			return map[string]any{}, nil
		}
		provider.connected = true
	}
	metrics := map[string]any{}
	for pid, definition := range StandardPIDs {
		lines, err := provider.adapter.Query(1, pid)
		if err != nil {
			provider.adapter.Close()
			provider.connected = false
			return metrics, nil
		}
		data := ParseOBDResponse(1, pid, lines)
		if data == nil {
			continue
		}
		value, err := definition.Decode(data)
		if err == nil {
			metrics[definition.Name] = value
		}
	}
	return metrics, nil
}
func (provider *StandardOBDProvider) Close() { provider.adapter.Close() }
