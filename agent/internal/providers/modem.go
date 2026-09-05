package providers

import (
	"fmt"
	"strconv"
	"strings"
	"time"

	"github.com/Buco7854/carhibou/agent/internal/model"
	"go.bug.st/serial"
)

// gnssCommandFamilies are tried in order because SIMCom firmware split the GNSS
// control surface: newer SIM7600 builds answer AT+CGPS, older ones AT+CGNSPWR.
// A module that rejects one usually accepts the other, and a module already
// powered on answers ERROR to the enable command without any harm done.
var gnssCommandFamilies = []struct {
	query   string
	enable  string
	disable string
	prefix  string
}{
	{query: "AT+CGPS?", enable: "AT+CGPS=1", disable: "AT+CGPS=0", prefix: "+CGPS:"},
	{query: "AT+CGNSPWR?", enable: "AT+CGNSPWR=1", disable: "AT+CGNSPWR=0", prefix: "+CGNSPWR:"},
}

var (
	openModemPort   = serial.Open
	gnssResetSettle = time.Second
)

const modemReadyAttempts = 3

// ModemPort is the control interface of a cellular module, used to switch the
// GNSS receiver on and, when the module publishes no separate NMEA stream, to
// poll a position directly.
type ModemPort struct {
	device string
	port   serial.Port
	buffer []byte
	// MaxAge discards a fix the module keeps replaying. Firmware answers
	// +CGPSINFO from its last known position rather than reporting empty fields
	// when the receiver loses the sky, so a poll is not proof of a live reading.
	MaxAge     time.Duration
	lastReport *time.Time
	lastChange time.Time
	lastAnswer time.Time
	failure    string
}

// Describe names this source for the journal line written when it goes live.
// A control port answering +CGPSINFO is the fallback, not the streamed path, so
// the journal has to say which of the two the agent settled on.
func (port *ModemPort) Describe() string {
	return "polled AT position on " + port.device
}

func NewModemPort(device string) *ModemPort {
	return &ModemPort{device: device, buffer: make([]byte, 512), MaxAge: DefaultFixMaxAge}
}

func (modem *ModemPort) Device() string { return modem.device }

func (modem *ModemPort) open() error {
	if modem.port != nil {
		return nil
	}
	port, err := openModemPort(modem.device, &serial.Mode{BaudRate: 115200})
	if err != nil {
		return err
	}
	if err := port.SetReadTimeout(300 * time.Millisecond); err != nil {
		port.Close()
		return err
	}
	modem.port = port
	return nil
}

func (modem *ModemPort) Close() {
	if modem.port != nil {
		modem.port.Close()
	}
	modem.port = nil
}

// Command writes one AT command and collects the reply until the module returns
// a final result code or the read window closes.
func (modem *ModemPort) Command(command string, window time.Duration) ([]string, error) {
	if err := modem.open(); err != nil {
		return nil, err
	}
	if err := modem.port.ResetInputBuffer(); err != nil {
		return nil, err
	}
	if _, err := modem.port.Write([]byte(strings.TrimSpace(command) + "\r")); err != nil {
		modem.Close()
		return nil, err
	}
	deadline := time.Now().Add(window)
	response := ""
	for time.Now().Before(deadline) {
		count, err := modem.port.Read(modem.buffer)
		if count > 0 {
			response += string(modem.buffer[:count])
			if isFinalResult(response) {
				modem.lastAnswer = time.Now()
				break
			}
		}
		if err != nil {
			modem.Close()
			return nil, err
		}
	}
	return responseLines(response, command), nil
}

// HasTraffic reports whether the control port completed an AT exchange. An
// empty +CGPSINFO position still proves the serial device is alive; lack of a
// satellite fix must not be escalated into a modem or USB reset.
func (modem *ModemPort) HasTraffic() bool { return !modem.lastAnswer.IsZero() }

func isFinalResult(response string) bool {
	return strings.Contains(response, "OK\r") || strings.Contains(response, "ERROR")
}

func responseLines(response, command string) []string {
	lines := []string{}
	for _, line := range strings.FieldsFunc(response, func(r rune) bool { return r == '\r' || r == '\n' }) {
		line = strings.TrimSpace(line)
		if line != "" && !strings.EqualFold(line, strings.TrimSpace(command)) {
			lines = append(lines, line)
		}
	}
	return lines
}

// waitReady wakes and verifies an AT control port before sending a state-changing
// command. A SIM7600 interface can ignore the first command after it has been
// reopened; treating that wake-up loss as rejection made recovery skip a control
// port that answered immediately in an interactive terminal.
func (modem *ModemPort) waitReady() error {
	for range modemReadyAttempts {
		lines, err := modem.Command("AT", 1500*time.Millisecond)
		if err == nil && containsFold(lines, "OK") {
			return nil
		}
		time.Sleep(200 * time.Millisecond)
	}
	return fmt.Errorf("the modem control port did not answer AT after %d attempts", modemReadyAttempts)
}

// EnableGNSS switches the receiver on. A module that boots with GNSS powered down
// publishes no NMEA at all, so without this the agent waits forever for a fix that
// the hardware was never asked to produce.
func (modem *ModemPort) EnableGNSS() (string, error) {
	if err := modem.waitReady(); err != nil {
		return "", err
	}
	var lastErr error
	for _, family := range gnssCommandFamilies {
		lines, err := modem.Command(family.enable, 3*time.Second)
		if err != nil {
			lastErr = err
			continue
		}
		if containsFold(lines, "OK") {
			return family.enable, nil
		}
		lastErr = fmt.Errorf("%s was rejected", family.enable)
	}
	if lastErr == nil {
		lastErr = fmt.Errorf("no GNSS enable command was accepted")
	}
	return "", lastErr
}

// GNSSEnabled reports whether the receiver is already running, so a caller can
// avoid re-issuing an enable command the module would answer with ERROR.
func (modem *ModemPort) GNSSEnabled() (bool, error) {
	if err := modem.waitReady(); err != nil {
		return false, err
	}
	var lastErr error
	for _, family := range gnssCommandFamilies {
		lines, err := modem.Command(family.query, 2*time.Second)
		if err != nil {
			lastErr = err
			continue
		}
		for _, line := range lines {
			if value, found := strings.CutPrefix(line, family.prefix); found {
				return strings.HasPrefix(strings.TrimSpace(value), "1"), nil
			}
		}
	}
	if lastErr != nil {
		return false, lastErr
	}
	return false, fmt.Errorf("the modem answered but reported no GNSS state")
}

// RestartGNSS cycles only the receiver engine, leaving the cellular modem and
// its data connection alone. It is used after a stream that previously worked
// has been silent long enough to be declared dead: merely asking whether GNSS
// is enabled cannot repair an enabled-but-wedged engine.
func (modem *ModemPort) RestartGNSS() (string, error) {
	if err := modem.waitReady(); err != nil {
		return "", err
	}
	var lastErr error
	for _, family := range gnssCommandFamilies {
		lines, err := modem.Command(family.disable, 3*time.Second)
		if err != nil {
			lastErr = err
			continue
		}
		if !containsFold(lines, "OK") {
			lastErr = fmt.Errorf("%s was rejected", family.disable)
			continue
		}
		time.Sleep(gnssResetSettle)
		lines, err = modem.Command(family.enable, 3*time.Second)
		if err == nil && containsFold(lines, "OK") {
			return family.disable + " then " + family.enable, nil
		}
		if err != nil {
			lastErr = err
		} else {
			lastErr = fmt.Errorf("%s was rejected", family.enable)
		}
	}
	if lastErr == nil {
		lastErr = fmt.Errorf("no GNSS control family was accepted")
	}
	return "", lastErr
}

// RestartModule asks the SIMCom firmware to reboot the composite modem. It is
// deliberately separate from RestartGNSS: callers should try the receiver-only
// cycle first because this command also interrupts the modem's USB interfaces
// and any cellular connection using them.
func (modem *ModemPort) RestartModule() error {
	if err := modem.waitReady(); err != nil {
		return err
	}
	lines, err := modem.Command("AT+CRESET", 3*time.Second)
	if err != nil {
		return err
	}
	if !containsFold(lines, "OK") {
		return fmt.Errorf("AT+CRESET was rejected")
	}
	return nil
}

// Read polls a position over AT, satisfying the agent's position provider.
// Modules that expose no dedicated NMEA interface still answer +CGPSINFO.
//
// Polling is not proof of freshness: firmware replays its last known fix, clock
// included, once the receiver stops tracking. The reported UTC field is therefore
// used as the liveness signal, and a reading whose clock has stopped advancing for
// longer than MaxAge is treated as no position rather than as the current one.
// Status explains why the control port is publishing no position. The modem is
// the position source itself when the module exposes no NMEA interface, so its
// failures have to reach the heartbeat the same way a receiver's do.
func (modem *ModemPort) Status() string { return modem.failure }

func (modem *ModemPort) Read() (*model.PositionFix, error) {
	lines, err := modem.Command("AT+CGPSINFO", 2*time.Second)
	if err != nil {
		modem.failure = fmt.Sprintf("modem %s stopped answering: %v", modem.device, err)
	} else {
		modem.failure = ""
	}
	if err != nil {
		return nil, err
	}
	for _, line := range lines {
		value, found := strings.CutPrefix(line, "+CGPSINFO:")
		if !found {
			continue
		}
		fix, parseErr := ParseCGPSINFO(value)
		if parseErr != nil || fix == nil {
			return nil, parseErr
		}
		return modem.track(fix), nil
	}
	return nil, nil
}

// track records whether the module's own clock advanced since the previous poll.
func (modem *ModemPort) track(fix *model.PositionFix) *model.PositionFix {
	now := time.Now()
	switch {
	case fix.RecordedAt == nil:
		// Without a clock there is nothing to compare, so the reading is taken at
		// face value and the caller still sees an age of zero.
		modem.lastChange = now
	case modem.lastReport == nil || !fix.RecordedAt.Equal(*modem.lastReport):
		modem.lastReport = fix.RecordedAt
		modem.lastChange = now
	}
	if modem.MaxAge > 0 && !modem.lastChange.IsZero() && now.Sub(modem.lastChange) > modem.MaxAge {
		return nil
	}
	return fix
}

// Age reports how long the module has been repeating the same reading.
func (modem *ModemPort) Age() time.Duration {
	if modem.lastChange.IsZero() {
		return 0
	}
	return time.Since(modem.lastChange)
}

// ParseCGPSINFO decodes the SIMCom position report.
//
// Layout: lat,N/S,lon,E/W,ddmmyy,hhmmss.s,altitude,speed over ground,course.
// Every field is empty until the receiver has a fix, which is reported as no
// position rather than as an error.
func ParseCGPSINFO(value string) (*model.PositionFix, error) {
	fields := strings.Split(strings.TrimSpace(value), ",")
	if len(fields) < 4 || fields[0] == "" || fields[2] == "" {
		return nil, nil
	}
	latitude, err := coordinate(fields[0], fields[1])
	if err != nil {
		return nil, err
	}
	longitude, err := coordinate(fields[2], fields[3])
	if err != nil {
		return nil, err
	}
	fix := &model.PositionFix{Latitude: latitude, Longitude: longitude}
	if len(fields) > 6 && fields[6] != "" {
		if altitude, err := strconv.ParseFloat(fields[6], 64); err == nil {
			fix.Altitude = &altitude
		}
	}
	if len(fields) > 7 && fields[7] != "" {
		// Speed over ground is reported in knots, like the NMEA sentences.
		if speed, err := strconv.ParseFloat(fields[7], 64); err == nil {
			speed *= knotsToKMH
			fix.Speed = &speed
		}
	}
	if len(fields) > 8 && fields[8] != "" {
		if course, err := strconv.ParseFloat(fields[8], 64); err == nil {
			fix.Heading = &course
		}
	}
	if len(fields) > 5 {
		if recordedAt, err := cgpsTime(fields[4], fields[5]); err == nil {
			fix.RecordedAt = recordedAt
		}
	}
	return fix, nil
}

func cgpsTime(date, clock string) (*time.Time, error) {
	if len(date) != 6 || len(clock) < 6 {
		return nil, fmt.Errorf("timestamp is incomplete")
	}
	return rmcTime(clock, date)
}

func containsFold(lines []string, value string) bool {
	for _, line := range lines {
		if strings.EqualFold(line, value) {
			return true
		}
	}
	return false
}
