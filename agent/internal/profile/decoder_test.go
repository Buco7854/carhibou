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

// Body, brake and tyre signals, taken from the same proven script. Nibbles and
// single bits are what most of them are, so an offset error shows up as a
// plausible-looking wrong answer rather than as a decode failure.
func TestBuiltInProfileDecodesBodyAndTyreSignals(t *testing.T) {
	decoder, err := FromFile(filepath.Join("..", "..", "profiles", "citroen-c-zero-v1.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	values := func(frame model.CANFrame) map[string]any {
		result := map[string]any{}
		for _, signal := range decoder.Decode(frame, nil) {
			result[signal.Name] = signal.Value
		}
		return result
	}

	// Byte 1 high nibble 6 is dipped beam, low nibble bit 2 raises main beam,
	// byte 2 bit 0 is a door.
	body := values(model.CANFrame{CANID: 0x424, Data: []byte{0, 0x64, 0x01, 0, 0, 0, 0, 0}})
	if body["vehicle.lights"] != "dipped" {
		t.Fatalf("lights=%v, want dipped", body["vehicle.lights"])
	}
	if body["vehicle.high_beam"] != true || body["vehicle.door_open"] != true {
		t.Fatalf("high_beam=%v door_open=%v", body["vehicle.high_beam"], body["vehicle.door_open"])
	}
	shut := values(model.CANFrame{CANID: 0x424, Data: []byte{0, 0x40, 0x00, 0, 0, 0, 0, 0}})
	if shut["vehicle.lights"] != "sidelights" || shut["vehicle.door_open"] != false || shut["vehicle.high_beam"] != false {
		t.Fatalf("shut=%#v", shut)
	}

	// Byte 3 collects the lamps: bit 0 handbrake, bit 4 tyre pressure.
	lamps := values(model.CANFrame{CANID: 0x384, Data: []byte{0, 0, 0, 0x11, 0, 0, 0, 0}})
	if lamps["vehicle.handbrake"] != true || lamps["tyre.warning"] != true {
		t.Fatalf("lamps=%#v", lamps)
	}
	clear := values(model.CANFrame{CANID: 0x384, Data: []byte{0, 0, 0, 0x00, 0, 0, 0, 0}})
	if clear["vehicle.handbrake"] != false || clear["tyre.warning"] != false {
		t.Fatalf("clear=%#v", clear)
	}

	// Pressure then temperature per wheel, clockwise from the front left.
	tyres := values(model.CANFrame{CANID: 0x3D3, Data: []byte{0x96, 0x50, 0x96, 0x50, 0x8C, 0x4B, 0x8C, 0x4B}})
	if pressure, _ := tyres["tyre.front_left_pressure"].(float64); math.Abs(pressure-2.355) > .001 {
		t.Fatalf("front left pressure=%v bar", tyres["tyre.front_left_pressure"])
	}
	if temperature, _ := tyres["tyre.rear_left_temperature"].(float64); math.Abs(temperature-25) > .001 {
		t.Fatalf("rear left temperature=%v", tyres["tyre.rear_left_temperature"])
	}
}
