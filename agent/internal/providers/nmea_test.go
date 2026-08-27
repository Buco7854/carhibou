package providers

import (
	"fmt"
	"math"
	"strings"
	"testing"
	"time"
)

func TestNMEAPositionAndAccuracy(t *testing.T) {
	fix, err := ParseNMEA("$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A")
	if err != nil {
		t.Fatal(err)
	}
	if math.Abs(fix.Latitude-48.1173) > .000001 || math.Abs(fix.Longitude-11.5166667) > .000001 || fix.Speed == nil || math.Abs(*fix.Speed-41.4848) > .0001 || fix.RecordedAt.Year() != 1994 {
		t.Fatalf("unexpected fix: %#v", fix)
	}
	parser := NMEAAccumulator{}
	if _, err := parser.Consume("$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47"); err != nil {
		t.Fatal(err)
	}
	accuracySentence := withChecksum("GPGST,123520.00,3.2,6.6,4.7,47.3,5.8,5.6,22.4")
	fix, err = parser.Consume(accuracySentence)
	if err != nil {
		t.Fatal(err)
	}
	if fix.Accuracy == nil || math.Abs(*fix.Accuracy-math.Hypot(5.8, 5.6)) > .0001 {
		t.Fatalf("accuracy = %#v", fix.Accuracy)
	}
}

func TestNMEARejectsInvalidFix(t *testing.T) {
	value := withChecksum("GPRMC,123519,V,4807.038,N,01131.000,E,0,0,230394,,,A")
	fix, err := ParseNMEA(value)
	if err != nil || fix != nil {
		t.Fatalf("fix=%#v err=%v", fix, err)
	}
	if _, err := ParseNMEA(value[:len(value)-2] + "00"); err == nil {
		t.Fatal("bad checksum accepted")
	}
}

func withChecksum(body string) string {
	var checksum byte
	for index := range len(body) {
		checksum ^= body[index]
	}
	return fmt.Sprintf("$%s*%02X", body, checksum)
}

// A receiver publishes many sentences between agent samples. The provider must
// report where the vehicle is now, not replay a backlog one line at a time.
func TestNMEADrainKeepsNewestFixFromABurst(t *testing.T) {
	provider := NewNMEAProvider("")
	burst := ""
	for _, minute := range []string{"4851.0000", "4852.0000", "4853.0000"} {
		burst += nmeaSentence("GPRMC,120000.00,A,"+minute+",N,00220.0000,E,0.0,0.0,250826,,,A") + "\r\n"
		burst += nmeaSentence("GPGSV,3,1,09,01,05,040,20") + "\r\n"
	}
	provider.consume(burst)

	fix := provider.Fix()
	if fix == nil {
		t.Fatal("expected a fix from the burst")
	}
	if math.Abs(fix.Latitude-48.8833333) > .0001 {
		t.Fatalf("latitude=%v, want the newest sentence in the burst", fix.Latitude)
	}
}

func TestNMEAReassemblesSentencesSplitAcrossReads(t *testing.T) {
	provider := NewNMEAProvider("")
	sentence := nmeaSentence("GPRMC,120000.00,A,4851.0000,N,00220.0000,E,0.0,0.0,250826,,,A")
	provider.consume(sentence[:12])
	if provider.Fix() != nil {
		t.Fatal("a half-received sentence must not produce a fix")
	}
	provider.consume(sentence[12:] + "\r\n")
	if provider.Fix() == nil {
		t.Fatal("expected the reassembled sentence to decode")
	}
}

func TestNMEAStopsReportingAFixTheReceiverAbandoned(t *testing.T) {
	provider := NewNMEAProvider("")
	provider.consume(nmeaSentence("GPRMC,120000.00,A,4851.0000,N,00220.0000,E,0.0,0.0,250826,,,A") + "\r\n")
	if provider.Fix() == nil {
		t.Fatal("expected a fresh fix")
	}
	provider.lastFix = time.Now().Add(-2 * DefaultFixMaxAge)
	if provider.Fix() != nil {
		t.Fatal("a fix older than MaxAge must not be reported as the current position")
	}
	if provider.Age() < DefaultFixMaxAge {
		t.Fatalf("Age()=%v, want the real elapsed time since the last fix", provider.Age())
	}
}

func TestNMEADiscardsUnboundedNoise(t *testing.T) {
	provider := NewNMEAProvider("")
	provider.consume(strings.Repeat("x", maxPending+10))
	if len(provider.pending) != 0 {
		t.Fatalf("pending=%d bytes, want the reassembly buffer to be bounded", len(provider.pending))
	}
}

func nmeaSentence(body string) string {
	var checksum byte
	for index := range len(body) {
		checksum ^= body[index]
	}
	return fmt.Sprintf("$%s*%02X", body, checksum)
}
