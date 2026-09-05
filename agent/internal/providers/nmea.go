package providers

import (
	"fmt"
	"math"
	"strconv"
	"strings"
	"time"

	"github.com/Buco7854/carhibou/agent/internal/model"
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

// DefaultFixMaxAge stops a stale fix from being reported as current. A receiver
// publishes position sentences about once a second, so several missed seconds
// means the antenna lost the sky rather than that the vehicle stopped moving.
const DefaultFixMaxAge = 10 * time.Second

// QuietWindow is how long a receiver may publish nothing decodable before the
// silence is worth saying out loud, and DeadWindow is how long before it is
// treated as a source that has to be reacquired. A receiver searching for a fix
// under cover is quiet; one whose module has wedged never comes back on its own.
const (
	QuietWindow = 30 * time.Second
	DeadWindow  = 3 * time.Minute
)

// maxPending bounds the reassembly buffer so a port emitting noise without any
// newline cannot grow it without limit on a 512 MB agent.
const maxPending = 4096

type NMEAProvider struct {
	device string
	port   serial.Port
	parser NMEAAccumulator
	// MaxAge discards a fix the receiver stopped refreshing. Zero keeps the last
	// fix indefinitely, which is only useful for replay and tests.
	MaxAge  time.Duration
	buffer  []byte
	pending string
	lastFix time.Time
	// lastSentence tracks receiver liveness independently from fix quality. A
	// SIM7600 under cover keeps emitting valid NMEA sentences with an invalid-fix
	// flag; restarting or USB-resetting that healthy stream cannot create a view
	// of the sky and only makes recovery less reliable.
	lastSentence time.Time
	// opened stamps when this provider first held the port, so a receiver that
	// has never produced a fix can be told from one that just did. Age alone
	// cannot: a zero lastFix and a fresh one both read as no elapsed time.
	opened  time.Time
	failure string
}

// Describe names this source for the journal line written when it goes live.
func (provider *NMEAProvider) Describe() string {
	return "streamed NMEA on " + provider.device
}

func NewNMEAProvider(device string) *NMEAProvider {
	return &NMEAProvider{device: device, MaxAge: DefaultFixMaxAge, buffer: make([]byte, 512)}
}

func (provider *NMEAProvider) open() error {
	if provider.port != nil {
		return nil
	}
	port, err := serial.Open(provider.device, &serial.Mode{BaudRate: 115200})
	if err != nil {
		return err
	}
	// A short timeout lets a drain finish as soon as the port goes quiet.
	if err := port.SetReadTimeout(150 * time.Millisecond); err != nil {
		port.Close()
		return err
	}
	provider.port = port
	provider.opened = time.Now()
	provider.failure = ""
	return nil
}

// Status explains why the provider is publishing no position, and is empty while
// it has nothing to explain. A receiver that stops for longer than any search
// plausibly takes is treated as gone so its owner reacquires it, because a
// SIMCom module that has wedged does not recover by being read from again.
func (provider *NMEAProvider) Status() string {
	if provider.failure != "" {
		return provider.failure
	}
	if quiet := provider.quietFor(); quiet > DeadWindow {
		return fmt.Sprintf("no NMEA sentences from %s for %s", provider.device, quiet.Round(time.Second))
	}
	return ""
}

// State names a receiver that is quiet but not yet presumed gone: under cover or
// still searching, which is ordinary and not a fault.
func (provider *NMEAProvider) State() string {
	if provider.failure != "" {
		return ""
	}
	quiet := provider.quietFor()
	if quiet <= QuietWindow || quiet > DeadWindow {
		return ""
	}
	return fmt.Sprintf("receiver quiet for %s", quiet.Round(time.Second))
}

// quietFor is how long the receiver has published no valid NMEA sentence,
// measured from the last sentence or, when there has never been one, from
// opening the port. Fix freshness is deliberately a separate clock.
func (provider *NMEAProvider) quietFor() time.Duration {
	since := provider.lastSentence
	if since.IsZero() {
		since = provider.opened
	}
	if since.IsZero() {
		return 0
	}
	return time.Since(since)
}

// Read returns the newest fix the receiver published since the previous call.
//
// A receiver emits roughly ten sentences per second across several types while the
// agent samples far less often. Consuming one line per sample would read an
// ever-growing backlog and report a position minutes behind the vehicle, so every
// buffered byte is consumed and only the newest fix survives.
func (provider *NMEAProvider) Read() (*model.PositionFix, error) {
	if err := provider.open(); err != nil {
		provider.failure = fmt.Sprintf("device %s failed to open: %v", provider.device, err)
		return nil, err
	}
	if err := provider.drain(); err != nil {
		provider.Close()
		provider.failure = fmt.Sprintf("device %s stopped answering: %v", provider.device, err)
		return nil, err
	}
	return provider.Fix(), nil
}

// PollFix drains the receiver and returns the current fix. It is Read under
// another name, declared separately so a source that cannot be read cheaply does
// not accidentally satisfy the interface that promises it can.
func (provider *NMEAProvider) PollFix() (*model.PositionFix, error) { return provider.Read() }

// Fix reports the last decoded position while it is still fresh enough to describe
// where the vehicle is now.
func (provider *NMEAProvider) Fix() *model.PositionFix {
	if provider.parser.LastFix == nil {
		return nil
	}
	if provider.MaxAge > 0 && !provider.lastFix.IsZero() && time.Since(provider.lastFix) > provider.MaxAge {
		return nil
	}
	return provider.parser.LastFix
}

// Age reports how long ago the receiver last produced a decodable fix.
func (provider *NMEAProvider) Age() time.Duration {
	if provider.lastFix.IsZero() {
		return 0
	}
	return time.Since(provider.lastFix)
}

// HasTraffic reports whether this open source has produced a checksum-valid
// NMEA sentence. It does not imply a satellite fix: diagnostics use the
// distinction to avoid power-cycling a healthy receiver merely because it is
// indoors.
func (provider *NMEAProvider) HasTraffic() bool { return !provider.lastSentence.IsZero() }

func (provider *NMEAProvider) drain() error {
	for {
		count, err := provider.port.Read(provider.buffer)
		if count > 0 {
			provider.consume(string(provider.buffer[:count]))
		}
		if err != nil {
			return err
		}
		// A zero-length read is the timeout firing, meaning the port is idle.
		if count < len(provider.buffer) {
			return nil
		}
	}
}

func (provider *NMEAProvider) consume(chunk string) {
	provider.pending += chunk
	for {
		index := strings.IndexAny(provider.pending, "\r\n")
		if index < 0 {
			break
		}
		line := provider.pending[:index]
		provider.pending = provider.pending[index+1:]
		if line == "" {
			continue
		}
		if validChecksum(line) {
			provider.lastSentence = time.Now()
		}
		if fix, err := provider.parser.Consume(line); err == nil && fix != nil {
			provider.lastFix = time.Now()
		}
	}
	if len(provider.pending) > maxPending {
		provider.pending = ""
	}
}

func (provider *NMEAProvider) Close() {
	if provider.port != nil {
		provider.port.Close()
	}
	provider.port = nil
	provider.pending = ""
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
