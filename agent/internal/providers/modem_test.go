package providers

import (
	"math"
	"testing"
	"time"

	"github.com/Buco7854/vehinode/agent/internal/model"
)

func TestParseCGPSINFOReportsNoFixBeforeTheReceiverHasOne(t *testing.T) {
	// The module answers with empty fields until it acquires satellites.
	fix, err := ParseCGPSINFO(" ,,,,,,,,")
	if err != nil || fix != nil {
		t.Fatalf("fix=%#v err=%v, want no fix and no error", fix, err)
	}
}

func TestParseCGPSINFODecodesAFix(t *testing.T) {
	fix, err := ParseCGPSINFO(" 4851.9950,N,00220.5312,E,250826,143012.0,89.6,10.0,270.0")
	if err != nil {
		t.Fatal(err)
	}
	if fix == nil {
		t.Fatal("expected a fix")
	}
	if math.Abs(fix.Latitude-48.866583) > .0001 || math.Abs(fix.Longitude-2.342187) > .0001 {
		t.Fatalf("latitude=%v longitude=%v", fix.Latitude, fix.Longitude)
	}
	if fix.Altitude == nil || math.Abs(*fix.Altitude-89.6) > .001 {
		t.Fatalf("altitude=%v", fix.Altitude)
	}
	// Speed over ground arrives in knots and is published in km/h like NMEA.
	if fix.Speed == nil || math.Abs(*fix.Speed-18.52) > .01 {
		t.Fatalf("speed=%v, want knots converted to km/h", fix.Speed)
	}
	if fix.Heading == nil || math.Abs(*fix.Heading-270) > .001 {
		t.Fatalf("heading=%v", fix.Heading)
	}
	if fix.RecordedAt == nil || fix.RecordedAt.Year() != 2026 || fix.RecordedAt.Day() != 25 {
		t.Fatalf("recordedAt=%v, want the ddmmyy date decoded", fix.RecordedAt)
	}
}

func TestParseCGPSINFORejectsAPartialCoordinate(t *testing.T) {
	if _, err := ParseCGPSINFO("48,N,00220.5312,E,250826,143012.0,,,"); err == nil {
		t.Fatal("expected an error for a coordinate shorter than its degree field")
	}
}

func TestResponseLinesDropsTheEcho(t *testing.T) {
	lines := responseLines("AT+CGPSINFO\r\r\n+CGPSINFO: ,,,,,,,,\r\n\r\nOK\r\n", "AT+CGPSINFO")
	if len(lines) != 2 || lines[0] != "+CGPSINFO: ,,,,,,,," || lines[1] != "OK" {
		t.Fatalf("lines=%#v", lines)
	}
}

func mustParse(t *testing.T, value string) *model.PositionFix {
	t.Helper()
	fix, err := ParseCGPSINFO(value)
	if err != nil || fix == nil {
		t.Fatalf("fix=%#v err=%v", fix, err)
	}
	return fix
}

// Real firmware answers +CGPSINFO from its last known position, clock included,
// after the receiver stops tracking. A frozen clock is the only signal that the
// reading is a replay rather than a live measurement.
func TestModemDropsAFixWhoseClockStoppedAdvancing(t *testing.T) {
	modem := NewModemPort("")
	modem.MaxAge = 30 * time.Second
	reading := " 4858.650431,N,00159.450966,E,250826,224704.0,38.2,0.0,"

	if modem.track(mustParse(t, reading)) == nil {
		t.Fatal("the first reading must be reported")
	}
	if modem.track(mustParse(t, reading)) == nil {
		t.Fatal("a repeat within MaxAge is still the best known position")
	}

	// The module has now been repeating the same clock for longer than MaxAge.
	modem.lastChange = time.Now().Add(-2 * modem.MaxAge)
	if modem.track(mustParse(t, reading)) != nil {
		t.Fatal("a reading whose clock never advanced must not be reported as current")
	}
	if modem.Age() < modem.MaxAge {
		t.Fatalf("Age()=%v, want the time since the reading last changed", modem.Age())
	}
}

// A parked vehicle keeps the same coordinates while its clock keeps ticking, which
// is a live fix and must never be discarded.
func TestModemKeepsAStationaryFixWhoseClockAdvances(t *testing.T) {
	modem := NewModemPort("")
	modem.MaxAge = 30 * time.Second
	modem.track(mustParse(t, " 4858.650431,N,00159.450966,E,250826,224704.0,38.2,0.0,"))
	modem.lastChange = time.Now().Add(-2 * modem.MaxAge)

	fix := modem.track(mustParse(t, " 4858.650431,N,00159.450966,E,250826,224804.0,38.2,0.0,"))
	if fix == nil {
		t.Fatal("a stationary vehicle with an advancing clock is still positioned")
	}
	if modem.Age() > time.Second {
		t.Fatalf("Age()=%v, want the age reset by the new reading", modem.Age())
	}
}
