package store

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

const (
	Auto = "auto"
	Off  = "off"
)

type Hardware struct {
	GPS string `json:"gps"`
	OBD string `json:"obd"`
	// Modem is the cellular control port used to switch the GNSS receiver on.
	// Empty means "discover it", which only happens while another role is auto.
	Modem string `json:"modem,omitempty"`
}

func DefaultHardware() Hardware { return Hardware{GPS: Auto, OBD: Auto} }

func (hardware Hardware) Validate() error {
	for source, value := range map[string]string{"GPS": hardware.GPS, "OBD": hardware.OBD} {
		if value == "" || value != Auto && value != Off && !strings.HasPrefix(value, "/dev/") {
			return fmt.Errorf("%s selection must be auto, off, or an absolute /dev path", source)
		}
	}
	if hardware.Modem != "" && hardware.Modem != Off && !strings.HasPrefix(hardware.Modem, "/dev/") {
		return fmt.Errorf("modem selection must be off or an absolute /dev path")
	}
	return nil
}

type HardwareStore struct{ Path string }

func (store HardwareStore) Load() (Hardware, error) {
	if _, err := os.Stat(store.Path); os.IsNotExist(err) {
		return DefaultHardware(), nil
	}
	var hardware Hardware
	if err := ReadJSON(store.Path, &hardware); err != nil {
		return hardware, fmt.Errorf("cannot load hardware configuration: %w", err)
	}
	if err := hardware.Validate(); err != nil {
		return hardware, fmt.Errorf("cannot load hardware configuration: %w", err)
	}
	return hardware, nil
}

func (store HardwareStore) Save(hardware Hardware) error {
	if err := hardware.Validate(); err != nil {
		return err
	}
	return WriteJSONAtomic(store.Path, hardware, 0o644)
}

func SerialCandidates() []string {
	patterns := []string{"/dev/serial/by-id/*", "/dev/ttyUSB*", "/dev/ttyACM*"}
	seen := map[string]bool{}
	var values []string
	for _, pattern := range patterns {
		matches, _ := filepath.Glob(pattern)
		sort.Strings(matches)
		for _, match := range matches {
			if !seen[match] {
				seen[match] = true
				values = append(values, match)
			}
		}
	}
	return values
}

// Detection is what the running service resolved at startup.
//
// The service holds the serial ports while it runs, so a diagnostic command cannot
// probe them itself without stopping it first. Publishing the result lets an
// operator see what was chosen without interrupting telemetry.
type Detection struct {
	At    string `json:"at"`
	GPS   string `json:"gps,omitempty"`
	OBD   string `json:"obd,omitempty"`
	Modem string `json:"modem,omitempty"`
	Ports any    `json:"ports,omitempty"`
}

type DetectionStore struct{ Path string }

func (store DetectionStore) Load() (Detection, bool) {
	var detection Detection
	if err := ReadJSON(store.Path, &detection); err != nil {
		return Detection{}, false
	}
	return detection, true
}

func (store DetectionStore) Save(detection Detection) error {
	return WriteJSONAtomic(store.Path, detection, 0o644)
}
