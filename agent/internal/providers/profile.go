package providers

import (
	"time"

	"github.com/Buco7854/vehinode/agent/internal/model"
	"github.com/Buco7854/vehinode/agent/internal/profile"
)

// connectRetryInterval throttles reconnection to an adapter that is not
// answering. Connect is six serial exchanges; attempting it on every sample
// means a tracker with an unplugged adapter spends most of its single core
// timing out, which delays the position samples it could still be taking.
const connectRetryInterval = 60 * time.Second

type ProfileProvider struct {
	adapter   *OBDAdapter
	decoder   *profile.DecoderEngine
	connected bool
	metrics   map[string]any
	failure   string
	nextTry   time.Time
	live      bool
}

func NewProfileProvider(adapter *OBDAdapter, decoder *profile.DecoderEngine) *ProfileProvider {
	return &ProfileProvider{adapter: adapter, decoder: decoder, metrics: map[string]any{}}
}

// Status explains why the provider is publishing nothing.
//
// Every failure here is recoverable and none of it should stop a tracker
// reporting its position, so ReadMetrics returns what it has rather than an
// error. That made a permanently disconnected adapter invisible: the vehicle
// published position and health forever and simply never mentioned CAN.
func (provider *ProfileProvider) Status() string { return provider.failure }

// Live reports whether a frame arrived during the last read.
//
// The decoded metrics cannot answer this: they are the last known values and are
// republished unchanged after the bus goes quiet, so a parked vehicle looks from
// the metrics alone exactly like a moving one.
func (provider *ProfileProvider) Live() bool { return provider.live }

func (provider *ProfileProvider) ReadMetrics() (map[string]any, error) {
	if !provider.connected {
		if time.Now().Before(provider.nextTry) {
			return copyMetrics(provider.metrics), nil
		}
		provider.nextTry = time.Now().Add(connectRetryInterval)
		if err := provider.adapter.Connect(); err != nil {
			provider.failure = "adapter did not connect: " + err.Error()
			return copyMetrics(provider.metrics), nil
		}
		if err := provider.adapter.SelectProtocol("6"); err != nil {
			provider.adapter.Close()
			provider.failure = "adapter rejected CAN protocol 6: " + err.Error()
			return copyMetrics(provider.metrics), nil
		}
		provider.connected = true
		provider.failure = ""
	}
	provider.live = false
	err := provider.adapter.Monitor(time.Second, func(frame model.CANFrame) {
		provider.live = true
		for _, decoded := range provider.decoder.Decode(frame, provider.metrics) {
			provider.metrics[decoded.Name] = decoded.Value
		}
	})
	if err != nil {
		provider.adapter.Close()
		provider.connected = false
		provider.failure = "CAN monitoring stopped: " + err.Error()
	} else if len(provider.metrics) == 0 {
		provider.failure = "adapter connected but the vehicle sent no matching CAN frames"
	}
	return copyMetrics(provider.metrics), nil
}

func (provider *ProfileProvider) Close() { provider.adapter.Close() }

func copyMetrics(source map[string]any) map[string]any {
	result := map[string]any{}
	for key, value := range source {
		result[key] = value
	}
	return result
}
