package providers

import (
	"strings"
	"testing"
	"time"

	"github.com/Buco7854/carhibou/agent/internal/model"
	"github.com/Buco7854/carhibou/agent/internal/profile"
	"go.bug.st/serial"
)

const oneSignal = `{"id":"t","signals":[{"name":"battery.soc","source":{"type":"can","can_id":884},
"decoder":{"byte_offset":1,"data_type":"uint8","scale":0.5,"offset":-5}}]}`

func testDecoder(t *testing.T) *profile.DecoderEngine {
	t.Helper()
	decoder, err := profile.ParseJSON([]byte(oneSignal))
	if err != nil {
		t.Fatal(err)
	}
	return decoder
}

func TestProfileObservationsKeepFrameTimesAndDerivedDependencyAge(t *testing.T) {
	decoder, err := profile.ParseJSON([]byte(`{
        "id":"derived-times",
        "signals":[
          {"name":"battery.pack_voltage","source":{"type":"can","can_id":1},"decoder":{"data_type":"uint8"}},
          {"name":"battery.current","source":{"type":"can","can_id":2},"decoder":{"data_type":"uint8"}}
        ],
        "computed_metrics":[{"name":"battery.power","operation":"multiply","inputs":["battery.pack_voltage","battery.current"]}]
    }`))
	if err != nil {
		t.Fatal(err)
	}
	provider := NewProfileProvider(NewOBDAdapter("/dev/carhibou-absent"), decoder)
	old := time.Date(2026, 8, 29, 1, 0, 0, 0, time.UTC)
	newer := old.Add(10 * time.Second)
	newest := old.Add(20 * time.Second)
	provider.record(model.CANFrame{Timestamp: float64(old.Unix()), CANID: 1, Data: []byte{10}})
	provider.record(model.CANFrame{Timestamp: float64(newer.Unix()), CANID: 2, Data: []byte{3}})
	provider.record(model.CANFrame{Timestamp: float64(newest.Unix()), CANID: 2, Data: []byte{4}})

	observations := provider.observations
	if got := observations["battery.pack_voltage"].Metadata.ObservedAt; !got.Equal(old) {
		t.Fatalf("voltage observed_at=%s want %s", got, old)
	}
	if got := observations["battery.current"].Metadata.ObservedAt; !got.Equal(newest) {
		t.Fatalf("current observed_at=%s want %s", got, newest)
	}
	power := observations["battery.power"]
	if power.Metadata.Method != model.MethodDerived || !power.Metadata.ObservedAt.Equal(old) {
		t.Fatalf("derived power metadata=%#v, want oldest dependency %s", power.Metadata, old)
	}
	if power.Value != float64(40) {
		t.Fatalf("derived power=%v want 40", power.Value)
	}
}

func TestProfileStartsMonitoringAndRetainsFramesBeforeTheFirstRead(t *testing.T) {
	port := &scriptedPort{replies: map[string]string{
		"ATZ":    "OK\r>",
		"ATE0":   "OK\r>",
		"ATL0":   "OK\r>",
		"ATS1":   "OK\r>",
		"ATH1":   "OK\r>",
		"STBRT":  "?\r>",
		"STFAP":  "OK\r>",
		"ATSP6":  "OK\r>",
		"ATCAF0": "OK\r>",
		"STM":    "374 8 00 90 00 00 00 00 00 00\r",
		"\r":     "STOPPED\r>",
	}}
	previousOpen := openOBDPort
	openOBDPort = func(string, *serial.Mode) (serial.Port, error) { return port, nil }
	t.Cleanup(func() { openOBDPort = previousOpen })

	provider := NewProfileProvider(NewOBDAdapter("scripted"), testDecoder(t))
	provider.trial = 25 * time.Millisecond
	defer provider.Close()
	provider.Start()

	provider.mutex.Lock()
	running := provider.stop != nil
	provider.mutex.Unlock()
	if !running {
		t.Fatal("profile monitor was not running when Start returned")
	}
	observations, err := provider.ReadObservations()
	if err != nil {
		t.Fatal(err)
	}
	if got := observations["battery.soc"].Value; got != float64(67) {
		t.Fatalf("first battery.soc=%v, want decoded frame captured during Start", got)
	}
}

// Sampling must not wait for the bus. Frames arrive continuously whether or not
// anyone is reading, and a window opened per sample both blocked for its whole
// duration — making a one-second cadence impossible — and saw only the fraction
// of the bus that fell inside it.
func TestReadMetricsDoesNotWaitForTheBus(t *testing.T) {
	provider := NewProfileProvider(NewOBDAdapter("/dev/carhibou-absent"), testDecoder(t))
	defer provider.Close()

	started := time.Now()
	for i := 0; i < 3; i++ {
		if _, err := provider.ReadObservations(); err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
	}
	// The adapter cannot open, so the first call fails fast and the rest are held
	// off by the retry interval. None of them may block on a monitor window.
	if elapsed := time.Since(started); elapsed > time.Second {
		t.Fatalf("three samples took %s; sampling is waiting on the bus", elapsed)
	}
	if status := provider.Status(); !strings.Contains(status, "failed to open") {
		t.Fatalf("status=%q, want the connection failure named", status)
	}
	if provider.Live() {
		t.Fatal("a provider that never saw a frame is not live")
	}
}

// A failing adapter must be retried on a timer rather than on every sample: on a
// single core, connecting is several serial exchanges and would crowd out the
// position samples the agent can still take.
func TestAFailedAdapterIsNotRetriedEverySample(t *testing.T) {
	provider := NewProfileProvider(NewOBDAdapter("/dev/carhibou-absent"), testDecoder(t))
	defer provider.Close()

	provider.ReadObservations()
	first := provider.nextTry
	provider.ReadObservations()
	if !provider.nextTry.Equal(first) {
		t.Fatal("the retry window was reset by a sample that should have been held off")
	}
	if time.Until(first) > connectRetryInterval {
		t.Fatalf("next attempt is %s away, beyond the %s interval", time.Until(first), connectRetryInterval)
	}
}

// Closing must be safe whether or not a monitor ever started, because an agent
// shuts down the same way after a good run and after a failed connection.
func TestClosingIsSafeWithoutAMonitor(t *testing.T) {
	provider := NewProfileProvider(NewOBDAdapter("/dev/carhibou-absent"), testDecoder(t))
	provider.Close()
	provider.Close()
}
