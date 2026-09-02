package runtime

import (
	"errors"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Buco7854/carhibou/agent/internal/model"
)

type fakePositionSource struct {
	mutex  sync.Mutex
	fix    *model.PositionFix
	status string
	state  string
	err    error
	closed int
}

func (source *fakePositionSource) Read() (*model.PositionFix, error) {
	source.mutex.Lock()
	defer source.mutex.Unlock()
	return source.fix, source.err
}

func (source *fakePositionSource) Status() string {
	source.mutex.Lock()
	defer source.mutex.Unlock()
	return source.status
}

func (source *fakePositionSource) State() string {
	source.mutex.Lock()
	defer source.mutex.Unlock()
	return source.state
}

func (source *fakePositionSource) Close() {
	source.mutex.Lock()
	defer source.mutex.Unlock()
	source.closed++
}

func fastPositionRetries(source *RetryingPositionProvider) {
	source.mutex.Lock()
	defer source.mutex.Unlock()
	source.retryInitial = 5 * time.Millisecond
	source.retryMaximum = 20 * time.Millisecond
	source.backoff = source.retryInitial
	source.healthPoll = 5 * time.Millisecond
}

// A vehicle that stops reporting its position must not look like a vehicle
// parked in a tunnel. Without this the only evidence of a missing receiver was
// the absence of fixes, which is also what a working receiver underground looks
// like.
func TestNoPositionDeviceIsReportedInEveryHeartbeat(t *testing.T) {
	source := NewRetryingPositionProvider(func() (PositionProvider, error) {
		return nil, errors.New("no GPS device found while probing /dev/serial/by-id/*")
	})
	defer source.Close()

	agent := newAgent(t, source)
	sample, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	reported, present := sample.Agent["position_source_error"]
	if !present {
		t.Fatalf("no position_source_error in %#v", sample.Agent)
	}
	if !strings.Contains(reported.(string), "no GPS device found") {
		t.Fatalf("position_source_error=%v, want the missing device named", reported)
	}
	if sample.Position != nil {
		t.Fatal("a missing receiver must not produce a position")
	}

	// And it keeps saying so rather than mentioning it once.
	second, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if _, present := second.Agent["position_source_error"]; !present {
		t.Fatal("the explanation lasted one heartbeat")
	}
}

// A receiver that has gone quiet but is not presumed gone is an ordinary state,
// not a fault, and says so without becoming an error.
func TestQuietReceiverIsAStateNotAnError(t *testing.T) {
	source := &fakePositionSource{state: "receiver quiet for 45s"}
	agent := newAgent(t, source)
	sample, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if sample.Agent["position_source_state"] != "receiver quiet for 45s" {
		t.Fatalf("position_source_state=%v", sample.Agent["position_source_state"])
	}
	if _, reported := sample.Agent["position_source_error"]; reported {
		t.Fatal("a quiet receiver is not an error")
	}
}

// The wedged-module case: nothing at first, then the port comes back. The agent
// has to pick it up without being restarted, and stop complaining once it has.
func TestPositionSourceIsReacquiredWhenTheDeviceAppears(t *testing.T) {
	var mutex sync.Mutex
	available := false
	source := NewRetryingPositionProvider(func() (PositionProvider, error) {
		mutex.Lock()
		defer mutex.Unlock()
		if !available {
			return nil, errors.New("no GPS device found while probing /dev/serial/by-id/*")
		}
		return &fakePositionSource{fix: &model.PositionFix{Latitude: 48.85, Longitude: 2.35}}, nil
	})
	defer source.Close()
	fastPositionRetries(source)
	source.Start()

	if source.Status() == "" {
		t.Fatal("a missing device should be reported while it is missing")
	}

	mutex.Lock()
	available = true
	mutex.Unlock()

	waitFor(t, func() bool { return source.Status() == "" })

	agent := newAgent(t, source)
	sample, err := agent.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if sample.Position == nil {
		t.Fatal("fixes should flow once the device is back")
	}
	if _, reported := sample.Agent["position_source_error"]; reported {
		t.Fatalf("the error outlived the fault: %v", sample.Agent["position_source_error"])
	}
}

// A source that fails while in use is dropped and reacquired, and the port it
// held is given back rather than leaked on every retry.
func TestFailingPositionSourceIsClosedAndReplaced(t *testing.T) {
	failing := &fakePositionSource{}
	var mutex sync.Mutex
	handed := 0
	source := NewRetryingPositionProvider(func() (PositionProvider, error) {
		mutex.Lock()
		defer mutex.Unlock()
		handed++
		if handed == 1 {
			return failing, nil
		}
		return &fakePositionSource{fix: &model.PositionFix{Latitude: 1, Longitude: 2}}, nil
	})
	defer source.Close()
	fastPositionRetries(source)
	source.Start()

	failing.mutex.Lock()
	failing.status = "device /dev/ttyUSB0 stopped answering"
	failing.mutex.Unlock()

	waitFor(t, func() bool { return source.Status() == "" })

	failing.mutex.Lock()
	closed := failing.closed
	failing.mutex.Unlock()
	if closed == 0 {
		t.Fatal("the failed source kept its port")
	}
	fix, err := source.Read()
	if err != nil || fix == nil {
		t.Fatalf("fix=%v err=%v, want the replacement to be reading", fix, err)
	}
}
