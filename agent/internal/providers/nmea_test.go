package providers

import (
	"fmt"
	"math"
	"testing"
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
