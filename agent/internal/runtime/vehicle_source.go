package runtime

import (
	"sync"
	"time"

	"github.com/Buco7854/carhibou/agent/internal/model"
)

const (
	initialVehicleRetry = 5 * time.Second
	maximumVehicleRetry = time.Minute
	vehicleHealthPoll   = time.Second
)

type VehicleAcquirer func() (VehicleProvider, error)

// RetryingVehicleProvider owns the replaceable vehicle-side connection used by
// the service. Hardware can enumerate after the process starts or disappear
// while it is running, so acquiring it is a lifecycle rather than startup work.
type RetryingVehicleProvider struct {
	acquire VehicleAcquirer

	mutex        sync.Mutex
	current      VehicleProvider
	failure      string
	backoff      time.Duration
	retryDelay   time.Duration
	retryInitial time.Duration
	retryMaximum time.Duration
	healthPoll   time.Duration
	started      bool
	closed       bool
	wake         chan struct{}
	stop         chan struct{}
	stopped      sync.WaitGroup
}

func NewRetryingVehicleProvider(acquire VehicleAcquirer) *RetryingVehicleProvider {
	return &RetryingVehicleProvider{
		acquire:      acquire,
		backoff:      initialVehicleRetry,
		retryInitial: initialVehicleRetry,
		retryMaximum: maximumVehicleRetry,
		healthPoll:   vehicleHealthPoll,
		wake:         make(chan struct{}, 1),
		stop:         make(chan struct{}),
	}
}

// Start makes the first acquisition synchronously so a successfully returned
// provider is already monitoring before the run loop takes its first sample.
// Later retries happen in the background and never delay GPS collection.
func (provider *RetryingVehicleProvider) Start() {
	provider.mutex.Lock()
	if provider.started || provider.closed {
		provider.mutex.Unlock()
		return
	}
	provider.started = true
	provider.mutex.Unlock()

	provider.attemptAcquire()
	provider.stopped.Add(1)
	go provider.retryLoop()
}

func (provider *RetryingVehicleProvider) ReadObservations() (model.MetricObservations, error) {
	provider.Start()
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	if provider.current == nil {
		return model.MetricObservations{}, nil
	}

	observations, err := provider.current.ReadObservations()
	if err != nil {
		provider.failLocked("vehicle source read failed: " + err.Error())
		provider.signalRetry()
		return model.MetricObservations{}, nil
	}
	if status := vehicleProviderStatus(provider.current); status != "" {
		provider.failLocked(status)
		provider.signalRetry()
	}
	return observations, nil
}

func (provider *RetryingVehicleProvider) Status() string {
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	if provider.failure != "" {
		return provider.failure
	}
	return vehicleProviderStatus(provider.current)
}

func (provider *RetryingVehicleProvider) State() string {
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	if provider.current == nil || provider.failure != "" {
		return ""
	}
	reporter, ok := provider.current.(VehicleState)
	if !ok {
		return ""
	}
	return reporter.State()
}

func (provider *RetryingVehicleProvider) Live() bool {
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	if provider.current == nil || provider.failure != "" {
		return false
	}
	live, ok := provider.current.(VehicleLiveness)
	return !ok || live.Live()
}

func (provider *RetryingVehicleProvider) Reset() {
	provider.mutex.Lock()
	provider.closeCurrentLocked()
	provider.failure = ""
	provider.retryDelay = 0
	provider.backoff = provider.retryInitial
	started := provider.started
	provider.mutex.Unlock()
	if started {
		provider.signalRetry()
	}
}

func (provider *RetryingVehicleProvider) Close() {
	provider.mutex.Lock()
	if provider.closed {
		provider.mutex.Unlock()
		return
	}
	provider.closed = true
	started := provider.started
	close(provider.stop)
	provider.mutex.Unlock()
	provider.signalRetry()
	if started {
		provider.stopped.Wait()
	}
	provider.mutex.Lock()
	provider.closeCurrentLocked()
	provider.mutex.Unlock()
}

func (provider *RetryingVehicleProvider) retryLoop() {
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
			timer := time.NewTimer(provider.healthPoll)
			select {
			case <-provider.wake:
				if !timer.Stop() {
					select {
					case <-timer.C:
					default:
					}
				}
				continue
			case <-provider.stop:
				if !timer.Stop() {
					select {
					case <-timer.C:
					default:
					}
				}
				return
			case <-timer.C:
				provider.mutex.Lock()
				if provider.current == current {
					if status := vehicleProviderStatus(current); status != "" {
						provider.failLocked(status)
					}
				}
				provider.mutex.Unlock()
				continue
			}
		}
		if delay > 0 {
			timer := time.NewTimer(delay)
			select {
			case <-timer.C:
			case <-provider.wake:
				if !timer.Stop() {
					select {
					case <-timer.C:
					default:
					}
				}
				continue
			case <-provider.stop:
				if !timer.Stop() {
					select {
					case <-timer.C:
					default:
					}
				}
				return
			}
		}
		provider.attemptAcquire()
	}
}

func (provider *RetryingVehicleProvider) attemptAcquire() {
	current, err := provider.acquire()
	if err != nil {
		provider.recordFailure(err.Error())
		return
	}
	if current == nil {
		provider.recordFailure("vehicle source acquisition returned no provider")
		return
	}
	if starter, ok := current.(VehicleStarter); ok {
		starter.Start()
	}
	if status := vehicleProviderStatus(current); status != "" {
		current.Close()
		provider.recordFailure(status)
		return
	}

	provider.mutex.Lock()
	if provider.closed || provider.current != nil {
		provider.mutex.Unlock()
		current.Close()
		return
	}
	provider.current = current
	provider.failure = ""
	provider.retryDelay = 0
	provider.backoff = provider.retryInitial
	provider.mutex.Unlock()
}

func (provider *RetryingVehicleProvider) recordFailure(reason string) {
	provider.mutex.Lock()
	defer provider.mutex.Unlock()
	provider.failure = reason
	provider.retryDelay = provider.backoff
	provider.backoff = min(provider.backoff*2, provider.retryMaximum)
}

func (provider *RetryingVehicleProvider) failLocked(reason string) {
	provider.closeCurrentLocked()
	provider.failure = reason
	provider.retryDelay = provider.backoff
	provider.backoff = min(provider.backoff*2, provider.retryMaximum)
}

func (provider *RetryingVehicleProvider) closeCurrentLocked() {
	if provider.current != nil {
		provider.current.Close()
		provider.current = nil
	}
}

func (provider *RetryingVehicleProvider) signalRetry() {
	select {
	case provider.wake <- struct{}{}:
	default:
	}
}

func vehicleProviderStatus(provider VehicleProvider) string {
	if provider == nil {
		return ""
	}
	reporter, ok := provider.(VehicleStatus)
	if !ok {
		return ""
	}
	return reporter.Status()
}
