package providers

import (
	"strings"
	"testing"
	"time"

	"github.com/Buco7854/vehinode/agent/internal/profile"
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

// Sampling must not wait for the bus. Frames arrive continuously whether or not
// anyone is reading, and a window opened per sample both blocked for its whole
// duration — making a one-second cadence impossible — and saw only the fraction
// of the bus that fell inside it.
func TestReadMetricsDoesNotWaitForTheBus(t *testing.T) {
	provider := NewProfileProvider(NewOBDAdapter("/dev/vehinode-absent"), testDecoder(t))
	defer provider.Close()

	started := time.Now()
	for i := 0; i < 3; i++ {
		if _, err := provider.ReadMetrics(); err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
	}
	// The adapter cannot open, so the first call fails fast and the rest are held
	// off by the retry interval. None of them may block on a monitor window.
	if elapsed := time.Since(started); elapsed > time.Second {
		t.Fatalf("three samples took %s; sampling is waiting on the bus", elapsed)
	}
	if status := provider.Status(); !strings.Contains(status, "did not connect") {
		t.Fatalf("status=%q, want the connection failure named", status)
	}
	if provider.Live() {
		t.Fatal("a provider that never saw a frame is not live")
	}
}

// A failing adapter must be retried on a timer rather than on every sample: on a
// single core, connecting is several serial exchanges and would crowd out the
// position samples the tracker can still take.
func TestAFailedAdapterIsNotRetriedEverySample(t *testing.T) {
	provider := NewProfileProvider(NewOBDAdapter("/dev/vehinode-absent"), testDecoder(t))
	defer provider.Close()

	provider.ReadMetrics()
	first := provider.nextTry
	provider.ReadMetrics()
	if !provider.nextTry.Equal(first) {
		t.Fatal("the retry window was reset by a sample that should have been held off")
	}
	if time.Until(first) > connectRetryInterval {
		t.Fatalf("next attempt is %s away, beyond the %s interval", time.Until(first), connectRetryInterval)
	}
}

// Closing must be safe whether or not a monitor ever started, because a tracker
// shuts down the same way after a good run and after a failed connection.
func TestClosingIsSafeWithoutAMonitor(t *testing.T) {
	provider := NewProfileProvider(NewOBDAdapter("/dev/vehinode-absent"), testDecoder(t))
	provider.Close()
	provider.Close()
}
