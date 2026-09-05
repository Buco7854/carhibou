package runtime

import (
	"errors"
	"math/rand"
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

func TestPositionReadAndShutdownDoNotWaitForAcquisition(t *testing.T) {
	entered := make(chan struct{})
	release := make(chan struct{})
	source := NewRetryingPositionProvider(func() (PositionProvider, error) {
		close(entered)
		<-release
		return nil, errors.New("receiver never answered")
	})
	source.Start()
	<-entered

	started := time.Now()
	if fix, err := source.Read(); err != nil || fix != nil {
		t.Fatalf("fix=%v err=%v", fix, err)
	}
	if elapsed := time.Since(started); elapsed > 100*time.Millisecond {
		t.Fatalf("read waited %s for acquisition", elapsed)
	}
	started = time.Now()
	source.Close()
	if elapsed := time.Since(started); elapsed > 100*time.Millisecond {
		t.Fatalf("shutdown waited %s for acquisition", elapsed)
	}
	close(release)
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
	source.Start()
	waitFor(t, func() bool { return source.Status() != "" })

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
	waitFor(t, func() bool { return source.Status() != "" })

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

func TestClosedPositionOwnerCannotBeginALateAcquisition(t *testing.T) {
	acquired := false
	source := NewRetryingPositionProvider(func() (PositionProvider, error) {
		acquired = true
		time.Sleep(400 * time.Millisecond)
		return &fakePositionSource{}, nil
	})
	source.Close()
	started := time.Now()
	source.attemptAcquire()
	if elapsed := time.Since(started); elapsed > 20*time.Millisecond {
		t.Fatalf("closed acquisition took %s", elapsed)
	}
	if acquired {
		t.Fatal("acquirer ran after Close won the lifecycle lock")
	}
}

// The same gap on the position side, where a retry that is signalled rather than
// timed out falls through to the acquisition as well.
func TestPositionCloseLandingOnTheRetryExpiryStaysBounded(t *testing.T) {
	for attempt := 0; attempt < closeRaceAttempts; attempt++ {
		source := NewRetryingPositionProvider(func() (PositionProvider, error) {
			time.Sleep(closeRaceAcquisition)
			return &fakePositionSource{}, nil
		})
		source.retryDelay = closeRaceRetryDelay
		source.Start()
		time.Sleep(jitteredRetryExpiry())
		started := time.Now()
		source.Close()
		if elapsed := time.Since(started); elapsed > closeRaceBound {
			t.Fatalf("Close attempt %d took %s, want under %s", attempt, elapsed, closeRaceBound)
		}
	}
}

const (
	closeRaceAttempts    = 400
	closeRaceRetryDelay  = 2 * time.Millisecond
	closeRaceAcquisition = 400 * time.Millisecond
	closeRaceBound       = 100 * time.Millisecond
	closeRaceJitter      = 400 * time.Microsecond
)

// jitteredRetryExpiry is a sleep centred on the retry delay, so repeated attempts
// walk across the instant the timer fires instead of all landing at one offset
// from it.
func jitteredRetryExpiry() time.Duration {
	return closeRaceRetryDelay - closeRaceJitter/2 + time.Duration(rand.Int63n(int64(closeRaceJitter)))
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
	waitFor(t, func() bool {
		mutex.Lock()
		defer mutex.Unlock()
		return handed == 1
	})

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
