package runtime

import (
	"sync"
	"time"

	"github.com/Buco7854/carhibou/agent/internal/model"
)

// PositionAcquirer opens a position source, or explains why it cannot.
type PositionAcquirer func() (PositionProvider, error)

// RetryingPositionProvider owns the replaceable position-side connection.
//
// It exists for the same reason its vehicle-side twin does, and for one the
// vehicle side does not have: a cellular module can wedge and cold-boot, coming
// back on different interface numbers with its receiver switched off. Before
// this, a module that went away took the agent's position with it until somebody
// restarted the service, and the agent said nothing about it either.
type RetryingPositionProvider struct {
	acquire PositionAcquirer

	mutex        sync.Mutex
	current      PositionProvider
	failure      string
	backoff      time.Duration
	retryDelay   time.Duration
	retryInitial time.Duration
	retryMaximum time.Duration
	healthPoll   time.Duration
	started      bool
	acquiring    bool
	closed       bool
	wake         chan struct{}
	stop         chan struct{}
	stopped      sync.WaitGroup
}

func NewRetryingPositionProvider(acquire PositionAcquirer) *RetryingPositionProvider {
	return &RetryingPositionProvider{
		acquire:      acquire,
		backoff:      initialVehicleRetry,
		retryInitial: initialVehicleRetry,
		retryMaximum: maximumVehicleRetry,
		healthPoll:   vehicleHealthPoll,
		wake:         make(chan struct{}, 1),
		stop:         make(chan struct{}),
	}
}

// Start puts every acquisition on the lifecycle goroutine. A serial sweep can
// take seconds and must not stand between the run loop and its next sample.
func (provider *RetryingPositionProvider) Start() {
	provider.mutex.Lock()
	if provider.started || provider.closed {
		provider.mutex.Unlock()
		return
	}
	provider.started = true
	provider.mutex.Unlock()

	provider.stopped.Add(1)
	go provider.retryLoop()
}

func (provider *RetryingPositionProvider) Read() (*model.PositionFix, error) {
	provider.Start()
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	if provider.current == nil {
		return nil, nil
	}
	fix, err := provider.current.Read()
	if err != nil {
		provider.failLocked("position source read failed: " + err.Error())
		provider.signalRetry()
		return nil, nil
	}
	if status := positionProviderStatus(provider.current); status != "" {
		provider.failLocked(status)
		provider.signalRetry()
		return nil, nil
	}
	return fix, nil
}

// PollFix forwards a cheap read to a source that offers one, so motion between
// samples stays noticeable through the retrying owner.
func (provider *RetryingPositionProvider) PollFix() (*model.PositionFix, error) {
	provider.mutex.Lock()
	poller, ok := provider.current.(PositionPoll)
	provider.mutex.Unlock()
	if !ok {
		return nil, nil
	}
	return poller.PollFix()
}

// Age reports the current source's fix age so a republished position stays
// distinguishable from a freshly measured one.
func (provider *RetryingPositionProvider) Age() time.Duration {
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	aged, ok := provider.current.(AgedPosition)
	if !ok {
		return 0
	}
	return aged.Age()
}

func (provider *RetryingPositionProvider) Status() string {
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	if provider.failure != "" {
		return provider.failure
	}
	return positionProviderStatus(provider.current)
}

func (provider *RetryingPositionProvider) State() string {
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	if provider.current == nil || provider.failure != "" {
		return ""
	}
	reporter, ok := provider.current.(PositionState)
	if !ok {
		return ""
	}
	return reporter.State()
}

func (provider *RetryingPositionProvider) Close() {
	provider.mutex.Lock()
	if provider.closed {
		provider.mutex.Unlock()
		return
	}
	provider.closed = true
	started := provider.started
	acquiring := provider.acquiring
	close(provider.stop)
	provider.mutex.Unlock()
	provider.signalRetry()
	// A late acquisition cannot be installed after closed is set, so shutdown
	// does not have to wait for a serial open that stopped answering.
	if started && !acquiring {
		provider.stopped.Wait()
	}
	provider.mutex.Lock()
	provider.closeCurrentLocked()
	provider.mutex.Unlock()
}

func (provider *RetryingPositionProvider) retryLoop() {
	defer provider.stopped.Done()
	for {
		provider.mutex.Lock()
		current := provider.current
		delay := provider.retryDelay
		closed := provider.closed
		provider.mutex.Unlock()
		if closed {
			return
		}
		if current != nil {
			if provider.waitFor(provider.healthPoll) {
				return
			}
			provider.mutex.Lock()
			if provider.current == current {
				if status := positionProviderStatus(current); status != "" {
					provider.failLocked(status)
				}
			}
			provider.mutex.Unlock()
			continue
		}
		if delay > 0 && provider.waitFor(delay) {
			return
		}
		provider.attemptAcquire()
	}
}

// waitFor sleeps until the timer fires, a retry is signalled, or the provider is
// closed. It reports whether the caller should stop.
func (provider *RetryingPositionProvider) waitFor(delay time.Duration) bool {
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-timer.C:
		return false
	case <-provider.wake:
		return false
	case <-provider.stop:
		return true
	}
}

func (provider *RetryingPositionProvider) attemptAcquire() {
	provider.mutex.Lock()
	if provider.closed {
		provider.mutex.Unlock()
		return
	}
	provider.acquiring = true
	provider.mutex.Unlock()
	defer func() {
		provider.mutex.Lock()
		provider.acquiring = false
		provider.mutex.Unlock()
	}()
	current, err := provider.acquire()
	if err != nil {
		provider.recordFailure(err.Error())
		return
	}
	if current == nil {
		provider.recordFailure("position source acquisition returned no provider")
		return
	}
	if status := positionProviderStatus(current); status != "" {
		closePosition(current)
		provider.recordFailure(status)
		return
	}

	provider.mutex.Lock()
	if provider.closed || provider.current != nil {
		provider.mutex.Unlock()
		closePosition(current)
		return
	}
	provider.current = current
	provider.failure = ""
	provider.retryDelay = 0
	provider.backoff = provider.retryInitial
	provider.mutex.Unlock()
}

func (provider *RetryingPositionProvider) recordFailure(reason string) {
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	provider.failure = reason
	provider.retryDelay = provider.backoff
	provider.backoff = min(provider.backoff*2, provider.retryMaximum)
}

func (provider *RetryingPositionProvider) failLocked(reason string) {
	provider.closeCurrentLocked()
	provider.failure = reason
	provider.retryDelay = provider.backoff
	provider.backoff = min(provider.backoff*2, provider.retryMaximum)
}

func (provider *RetryingPositionProvider) closeCurrentLocked() {
	if provider.current != nil {
		closePosition(provider.current)
		provider.current = nil
	}
}

func (provider *RetryingPositionProvider) signalRetry() {
	select {
	case provider.wake <- struct{}{}:
	default:
	}
}

// ClosablePosition is implemented by a source holding a port it must give back.
type ClosablePosition interface {
	Close()
}

func closePosition(provider PositionProvider) {
	if closer, ok := provider.(ClosablePosition); ok {
		closer.Close()
	}
}

func positionProviderStatus(provider PositionProvider) string {
	if provider == nil {
		return ""
	}
	reporter, ok := provider.(PositionStatus)
	if !ok {
		return ""
	}
	return reporter.Status()
}
