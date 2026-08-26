package profile

import (
	"math"
	"path/filepath"
	"testing"

	"github.com/Buco7854/vehinode/agent/internal/model"
)

func TestBuiltInProfileDecode(t *testing.T) {
	decoder, err := FromFile(filepath.Join("..", "..", "profiles", "citroen-c-zero-v1.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	// Charge is byte 1. Byte 0 is something else, which is why a frame carrying
	// the value there decodes to nothing.
	decoded := decoder.Decode(model.CANFrame{CANID: 0x374, Data: []byte{0, 0x96, 0, 0, 0, 0, 0, 0}}, nil)
	if len(decoded) != 1 || decoded[0].Name != "battery.soc" || math.Abs(decoded[0].Value.(float64)-70) > .001 {
		t.Fatalf("decoded=%#v", decoded)
	}
	decoded = decoder.Decode(model.CANFrame{CANID: 0x373, Data: []byte{0, 0, 0x80, 0x64, 0x0c, 0xe4, 0, 0}}, nil)
	values := map[string]float64{}
	for _, signal := range decoded {
		values[signal.Name] = signal.Value.(float64)
	}
	// (0x8064 - 0x8000) / 100 = +1.0 A, the direction the proven script reports.
	if math.Abs(values["battery.current"]-1) > .001 || math.Abs(values["battery.pack_voltage"]-330) > .001 {
		t.Fatalf("values=%#v", values)
	}
	// 330 V times 1 A is 330 W, which the profile scale publishes as 0.33 kW.
	if math.Abs(values["battery.power"]-0.33) > .001 {
		t.Fatalf("battery.power=%v, want 0.33 kW", values["battery.power"])
	}
	for _, signal := range decoded {
		if signal.Name == "battery.power" && signal.Unit != "kW" {
			t.Fatalf("battery.power unit=%q, want kW", signal.Unit)
		}
	}
}

// The identifiers a monitor filters on come from the profile, so a signal added
// without its frame reaching the adapter would be silently undecodable.
func TestProfileNamesTheIdentifiersItNeeds(t *testing.T) {
	decoder, err := FromFile(filepath.Join("..", "..", "profiles", "citroen-c-zero-v1.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	ids := decoder.CANIDs()
	for _, wanted := range []int{0x101, 0x298, 0x346, 0x373, 0x374, 0x389, 0x412} {
		found := false
		for _, id := range ids {
			found = found || id == wanted
		}
		if !found {
			t.Fatalf("identifiers %#x do not include %#x", ids, wanted)
		}
	}
	for index := 1; index < len(ids); index++ {
		if ids[index-1] >= ids[index] {
			t.Fatalf("identifiers are not in a stable order: %#x", ids)
		}
	}
}
