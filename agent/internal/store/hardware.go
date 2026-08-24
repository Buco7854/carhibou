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
}

func DefaultHardware() Hardware { return Hardware{GPS: Auto, OBD: Auto} }

func (hardware Hardware) Validate() error {
	for source, value := range map[string]string{"GPS": hardware.GPS, "OBD": hardware.OBD} {
		if value == "" || value != Auto && value != Off && !strings.HasPrefix(value, "/dev/") {
			return fmt.Errorf("%s selection must be auto, off, or an absolute /dev path", source)
		}
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

func GPSCandidates() []string {
	all := SerialCandidates()
	return prioritize(all,
		func(path string) bool { return strings.Contains(strings.ToLower(path), "simtech") },
		func(path string) bool { return path == "/dev/ttyUSB1" },
		func(path string) bool {
			lower := strings.ToLower(path)
			return !strings.Contains(lower, "obdlink") && !strings.Contains(lower, "ftdi")
		},
	)
}

func OBDCandidates() []string {
	all := SerialCandidates()
	return prioritize(all,
		func(path string) bool {
			lower := strings.ToLower(path)
			return strings.Contains(lower, "obdlink") || strings.Contains(lower, "ftdi")
		},
		func(path string) bool { return !strings.Contains(strings.ToLower(path), "simtech") },
	)
}

func prioritize(all []string, groups ...func(string) bool) []string {
	used := map[string]bool{}
	result := []string{}
	for _, group := range groups {
		for _, value := range all {
			if !used[value] && group(value) {
				used[value] = true
				result = append(result, value)
			}
		}
	}
	return result
}

func Resolve(selection string, candidates []string) string {
	if selection == Off {
		return ""
	}
	if selection == Auto {
		if len(candidates) == 0 {
			return ""
		}
		return candidates[0]
	}
	return selection
}
