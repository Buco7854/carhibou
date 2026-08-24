package runtime

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/Buco7854/vehinode/agent/internal/client"
	"github.com/Buco7854/vehinode/agent/internal/model"
	"github.com/Buco7854/vehinode/agent/internal/store"
)

type PositionProvider interface {
	Read() (*model.PositionFix, error)
}
type VehicleProvider interface {
	ReadMetrics() (map[string]any, error)
	Close()
}

type EmptyPosition struct{}

func (EmptyPosition) Read() (*model.PositionFix, error) { return nil, nil }

type EmptyVehicle struct{}

func (EmptyVehicle) ReadMetrics() (map[string]any, error) { return map[string]any{}, nil }
func (EmptyVehicle) Close()                               {}

type Agent struct {
	Queue    *store.Queue
	Client   *client.Client
	Position PositionProvider
	Vehicle  VehicleProvider
	BootID   string
	Sequence int64
}

func (agent *Agent) Collect() (model.Sample, error) {
	position, _ := agent.Position.Read()
	metrics, _ := agent.Vehicle.ReadMetrics()
	depth, _ := agent.Queue.Depth()
	sample := model.NewSample(agent.Sequence+1, position, metrics, SystemHealth(depth))
	agent.Sequence++
	return sample, agent.Queue.Enqueue(sample)
}

func (agent *Agent) Upload(limit int) (int64, error) {
	samples, err := agent.Queue.Pending(limit)
	if err != nil || len(samples) == 0 {
		return 0, err
	}
	acknowledged, err := agent.Client.Upload(agent.BootID, samples)
	if err != nil {
		return 0, err
	}
	return agent.Queue.Acknowledge(acknowledged)
}

func SystemHealth(queueDepth int) map[string]any {
	hostname, _ := os.Hostname()
	result := map[string]any{"hostname": hostname, "queue_depth": queueDepth}
	if source, err := os.Open("/proc/loadavg"); err == nil {
		scanner := bufio.NewScanner(source)
		scanner.Split(bufio.ScanWords)
		if scanner.Scan() {
			if value, err := strconv.ParseFloat(scanner.Text(), 64); err == nil {
				result["load_1m"] = value
			}
		}
		source.Close()
	}
	if content, err := os.ReadFile("/sys/class/thermal/thermal_zone0/temp"); err == nil {
		if value, err := strconv.ParseFloat(strings.TrimSpace(string(content)), 64); err == nil {
			result["cpu_temperature"] = float64(int(value/100)) / 10
		}
	}
	return result
}

func LastSequence(queue *store.Queue) (int64, error) {
	return queue.LastSequence()
}

func ValidateDistinctDevices(gps, obd string) error {
	if gps == "" || obd == "" {
		return nil
	}
	gpsPath, gpsErr := filepath.EvalSymlinks(gps)
	if gpsErr != nil {
		gpsPath = filepath.Clean(gps)
	}
	obdPath, obdErr := filepath.EvalSymlinks(obd)
	if obdErr != nil {
		obdPath = filepath.Clean(obd)
	}
	if gpsPath == obdPath {
		return fmt.Errorf("GPS and OBD cannot use the same serial device")
	}
	return nil
}
