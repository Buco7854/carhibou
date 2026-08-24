package providers

import (
	"bufio"
	"fmt"
	"math"
	"strconv"
	"strings"
	"time"

	"github.com/Buco7854/vehinode/agent/internal/model"
	"go.bug.st/serial"
)

const knotsToKMH = 1.852

func ParseNMEA(sentence string) (*model.PositionFix, error) {
	line := strings.TrimSpace(sentence)
	if !validChecksum(line) {
		return nil, fmt.Errorf("NMEA checksum is missing or invalid")
	}
	fields := strings.Split(strings.SplitN(line, "*", 2)[0], ",")
	if len(fields) == 0 || len(fields[0]) < 3 {
		return nil, nil
	}
	sentenceType := fields[0][len(fields[0])-3:]
	switch sentenceType {
	case "RMC":
		if len(fields) < 10 || fields[2] != "A" {
			return nil, nil
		}
		latitude, err := coordinate(fields[3], fields[4])
		if err != nil {
			return nil, err
		}
		longitude, err := coordinate(fields[5], fields[6])
		if err != nil {
			return nil, err
		}
		fix := &model.PositionFix{Latitude: latitude, Longitude: longitude}
		if fields[7] != "" {
			value, err := strconv.ParseFloat(fields[7], 64)
			if err != nil {
				return nil, err
			}
			value *= knotsToKMH
			fix.Speed = &value
		}
		if fields[8] != "" {
			value, err := strconv.ParseFloat(fields[8], 64)
			if err != nil {
				return nil, err
			}
			fix.Heading = &value
		}
		if recordedAt, err := rmcTime(fields[1], fields[9]); err == nil {
			fix.RecordedAt = recordedAt
		}
		return fix, nil
	case "GGA":
		if len(fields) < 10 {
			return nil, fmt.Errorf("GGA sentence is incomplete")
		}
		quality, err := strconv.Atoi(defaultString(fields[6], "0"))
		if err != nil {
			return nil, err
		}
		if quality <= 0 {
			return nil, nil
		}
		latitude, err := coordinate(fields[2], fields[3])
		if err != nil {
			return nil, err
		}
		longitude, err := coordinate(fields[4], fields[5])
		if err != nil {
			return nil, err
		}
		fix := &model.PositionFix{Latitude: latitude, Longitude: longitude, FixQuality: &quality}
		if fields[7] != "" {
			value, err := strconv.Atoi(fields[7])
			if err != nil {
				return nil, err
			}
			fix.Satellites = &value
		}
		if fields[9] != "" {
			value, err := strconv.ParseFloat(fields[9], 64)
			if err != nil {
				return nil, err
			}
			fix.Altitude = &value
		}
		return fix, nil
	default:
		return nil, nil
	}
}

func ParseGSTAccuracy(sentence string) (*float64, error) {
	line := strings.TrimSpace(sentence)
	if !validChecksum(line) {
		return nil, fmt.Errorf("NMEA checksum is missing or invalid")
	}
	fields := strings.Split(strings.SplitN(line, "*", 2)[0], ",")
	if len(fields) == 0 || !strings.HasSuffix(fields[0], "GST") || len(fields) < 8 || fields[6] == "" || fields[7] == "" {
		return nil, nil
	}
	latitude, err := strconv.ParseFloat(fields[6], 64)
	if err != nil {
		return nil, err
	}
	longitude, err := strconv.ParseFloat(fields[7], 64)
	if err != nil {
		return nil, err
	}
	value := math.Hypot(latitude, longitude)
	return &value, nil
}

type NMEAAccumulator struct{ LastFix *model.PositionFix }

func (parser *NMEAAccumulator) Consume(sentence string) (*model.PositionFix, error) {
	accuracy, err := ParseGSTAccuracy(sentence)
	if err == nil && accuracy != nil && parser.LastFix != nil {
		copy := *parser.LastFix
		copy.Accuracy = accuracy
		parser.LastFix = &copy
		return parser.LastFix, nil
	}
	fix, err := ParseNMEA(sentence)
	if err != nil || fix == nil {
		return fix, err
	}
	if previous := parser.LastFix; previous != nil && math.Abs(previous.Latitude-fix.Latitude) < .001 && math.Abs(previous.Longitude-fix.Longitude) < .001 {
		if fix.RecordedAt == nil {
			fix.RecordedAt = previous.RecordedAt
		}
		if fix.Altitude == nil {
			fix.Altitude = previous.Altitude
		}
		if fix.Speed == nil {
			fix.Speed = previous.Speed
		}
		if fix.Heading == nil {
			fix.Heading = previous.Heading
		}
		if fix.Accuracy == nil {
			fix.Accuracy = previous.Accuracy
		}
		if fix.FixQuality == nil {
			fix.FixQuality = previous.FixQuality
		}
		if fix.Satellites == nil {
			fix.Satellites = previous.Satellites
		}
	}
	parser.LastFix = fix
	return fix, nil
}

type NMEAProvider struct {
	device string
	port   serial.Port
	reader *bufio.Reader
	parser NMEAAccumulator
}

func NewNMEAProvider(device string) *NMEAProvider { return &NMEAProvider{device: device} }

func (provider *NMEAProvider) Read() (*model.PositionFix, error) {
	if provider.port == nil {
		port, err := serial.Open(provider.device, &serial.Mode{BaudRate: 115200})
		if err != nil {
			return nil, err
		}
		if err := port.SetReadTimeout(2 * time.Second); err != nil {
			port.Close()
			return nil, err
		}
		provider.port = port
		provider.reader = bufio.NewReader(port)
	}
	line, err := provider.reader.ReadString('\n')
	if err != nil {
		provider.Close()
		return nil, err
	}
	fix, err := provider.parser.Consume(line)
	if err != nil {
		return nil, err
	}
	return fix, nil
}

func (provider *NMEAProvider) Close() {
	if provider.port != nil {
		provider.port.Close()
	}
	provider.port = nil
	provider.reader = nil
}

func validChecksum(sentence string) bool {
	if !strings.HasPrefix(sentence, "$") || !strings.Contains(sentence, "*") {
		return false
	}
	parts := strings.SplitN(strings.TrimPrefix(sentence, "$"), "*", 2)
	if len(parts) != 2 || len(parts[1]) < 2 {
		return false
	}
	var value byte
	for index := range len(parts[0]) {
		value ^= parts[0][index]
	}
	expected, err := strconv.ParseUint(parts[1][:2], 16, 8)
	return err == nil && byte(expected) == value
}

func coordinate(value, hemisphere string) (float64, error) {
	if value == "" || !strings.Contains("NSEW", hemisphere) {
		return 0, fmt.Errorf("coordinate is incomplete")
	}
	degreeDigits := 2
	if hemisphere == "E" || hemisphere == "W" {
		degreeDigits = 3
	}
	if len(value) <= degreeDigits {
		return 0, fmt.Errorf("coordinate is incomplete")
	}
	degrees, err := strconv.Atoi(value[:degreeDigits])
	if err != nil {
		return 0, err
	}
	minutes, err := strconv.ParseFloat(value[degreeDigits:], 64)
	if err != nil {
		return 0, err
	}
	result := float64(degrees) + minutes/60
	if hemisphere == "S" || hemisphere == "W" {
		result = -result
	}
	return result, nil
}

func rmcTime(clock, date string) (*time.Time, error) {
	if len(clock) < 6 || len(date) != 6 {
		return nil, fmt.Errorf("timestamp is incomplete")
	}
	year, err := strconv.Atoi(date[4:])
	if err != nil {
		return nil, err
	}
	if year >= 80 {
		year += 1900
	} else {
		year += 2000
	}
	month, _ := strconv.Atoi(date[2:4])
	day, _ := strconv.Atoi(date[:2])
	hour, _ := strconv.Atoi(clock[:2])
	minute, _ := strconv.Atoi(clock[2:4])
	second, _ := strconv.Atoi(clock[4:6])
	nanoseconds := 0
	if dot := strings.IndexByte(clock, '.'); dot >= 0 {
		fraction := clock[dot+1:]
		if len(fraction) > 9 {
			fraction = fraction[:9]
		}
		fraction += strings.Repeat("0", 9-len(fraction))
		nanoseconds, _ = strconv.Atoi(fraction)
	}
	value := time.Date(year, time.Month(month), day, hour, minute, second, nanoseconds, time.UTC)
	return &value, nil
}

func defaultString(value, fallback string) string {
	if value == "" {
		return fallback
	}
	return value
}
