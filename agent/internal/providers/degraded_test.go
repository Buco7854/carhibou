package providers

import (
	"strings"
	"testing"
	"time"

	"github.com/Buco7854/carhibou/agent/internal/model"
)

// pidPort answers the commands it was given and NO DATA to everything else, the
// way an adapter in front of a vehicle that supports only some standard PIDs
// does. Silence means a missing adapter, so a fixture that stays quiet for an
// unsupported PID would be testing a different failure.
type pidPort struct {
	scriptedPort
	replies map[string]string
}

func (port *pidPort) Write(payload []byte) (int, error) {
	command := strings.TrimSpace(string(payload))
	if reply, ok := port.replies[command]; ok {
		port.pending = reply
		return len(payload), nil
	}
	port.pending = "NO DATA\r>"
	return len(payload), nil
}

// A vehicle with no profile is the ordinary case for anything that is not a
// C-Zero: standard PIDs and the adapter's own supply are what it has, and both
// have to arrive without a profile existing anywhere.
func TestStandardOBDVehicleReportsPIDsAndSupplyWithoutAProfile(t *testing.T) {
	// A real adapter answers NO DATA for a PID the vehicle does not support, which
	// is what makes a partial answer ordinary rather than a fault.
	port := &pidPort{replies: map[string]string{
		"ATRV": "12.6V\r>",
		"010C": "7E8 04 41 0C 1A F8\r>",
		"010D": "7E8 03 41 0D 32\r>",
	}}
	adapter := NewOBDAdapter("scripted")
	adapter.port = port
	adapter.CommandWindow = 200 * time.Millisecond

	provider := NewStandardOBDProvider(adapter)
	provider.connected = true
	observations, err := provider.ReadObservations()
	if err != nil {
		t.Fatal(err)
	}

	supply, present := observations[AuxVoltageMetric]
	if !present {
		t.Fatalf("no %s in %#v", AuxVoltageMetric, observations)
	}
	if supply.Value != 12.6 {
		t.Fatalf("aux voltage=%v, want 12.6", supply.Value)
	}
	if supply.Metadata.Channel != model.ChannelOBD {
		t.Fatalf("aux voltage channel=%q, want %q", supply.Metadata.Channel, model.ChannelOBD)
	}
	speed, present := observations["vehicle.speed"]
	if !present || speed.Value != 50.0 {
		t.Fatalf("vehicle.speed=%#v, want 50 from PID 0D", speed)
	}
	if provider.Status() != "" {
		t.Fatalf("a working standard adapter reported a failure: %q", provider.Status())
	}
}

// An adapter answering nothing at all must still not be mistaken for a working
// one, because a standard-OBD vehicle has no frames to fall back on.
func TestStandardOBDVehicleWithNoAnswersPublishesNothingAndSaysWhy(t *testing.T) {
	port := &scriptedPort{replies: map[string]string{}}
	adapter := NewOBDAdapter("scripted")
	adapter.port = port
	adapter.CommandWindow = 20 * time.Millisecond

	provider := NewStandardOBDProvider(adapter)
	provider.connected = true
	observations, err := provider.ReadObservations()
	if err != nil {
		t.Fatal(err)
	}
	if len(observations) != 0 {
		t.Fatalf("silent adapter published %#v", observations)
	}
	if provider.Status() == "" {
		t.Fatal("a silent adapter must say why it published nothing")
	}
}
