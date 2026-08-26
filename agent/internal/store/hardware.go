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

// SerialCandidates lists each serial device once, preferring its by-id name.
//
// A device appears under several paths: /dev/ttyUSB2 is also a /dev/serial/by-id
// symlink, and a four-interface modem contributes both forms for each interface.
// Deduplicating by the path they resolve to halves a probe sweep, which is worth
// having when every candidate costs a couple of seconds on a single core. The
// by-id name is kept because it survives a reboot reordering the ttyUSB numbers.
func SerialCandidates() []string {
	patterns := []string{"/dev/serial/by-id/*", "/dev/ttyUSB*", "/dev/ttyACM*"}
	seen := map[string]bool{}
	var values []string
	for _, pattern := range patterns {
		matches, _ := filepath.Glob(pattern)
		sort.Strings(matches)
		for _, match := range matches {
			resolved, err := filepath.EvalSymlinks(match)
			if err != nil {
				resolved = match
			}
			if !seen[resolved] {
				seen[resolved] = true
				values = append(values, match)
			}
		}
	}
	return values
}

// Detection is what the service resolved, kept so it need not be resolved again.
//
// It serves two purposes. The service holds the serial ports while it runs, so a
// diagnostic cannot probe them without stopping it first; publishing the result
// lets an operator see what was chosen without interrupting telemetry. And a sweep
// costs seconds per port, all of it spent waiting, which is not worth repeating on
// every restart of a service that lives on a single slow core.
type Detection struct {
	At    string `json:"at"`
	GPS   string `json:"gps,omitempty"`
	OBD   string `json:"obd,omitempty"`
	Modem string `json:"modem,omitempty"`
	// GPSStreams records whether the GPS path publishes sentences by itself, since
	// that decides whether its position is streamed or polled over AT.
	GPSStreams bool `json:"gps_streams,omitempty"`
	// Candidates is the port list the sweep was made against. A different list
	// means hardware was added, removed or renumbered underneath the answer.
	Candidates []string `json:"candidates,omitempty"`
	Ports      any      `json:"ports,omitempty"`
}

// Usable reports whether a stored detection can still be trusted without probing.
//
// Two cheap checks, neither of which opens a port: the set of candidates has to be
// the one the answer was made against, and every path the answer names has to
// still exist. A tracker that was replugged into a different socket, or a module
// that enumerated its interfaces in another order, fails the first; a device that
// simply went away fails the second.
func (detection Detection) Usable(candidates []string) bool {
	if len(detection.Candidates) != len(candidates) {
		return false
	}
	for index, candidate := range candidates {
		if detection.Candidates[index] != candidate {
			return false
		}
	}
	for _, device := range []string{detection.GPS, detection.OBD, detection.Modem} {
		if device == "" {
			continue
		}
		if _, err := os.Stat(device); err != nil {
			return false
		}
	}
	return len(candidates) > 0
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

// Forget discards the stored answer so the next start works it out again.
//
// The structural checks in Usable cannot catch a path that still exists and still
// enumerates the same but no longer behaves as it did. Failing to open what the
// answer named is the evidence for that, and throwing the answer away is what lets
// a restart recover instead of failing the same way forever.
func (store DetectionStore) Forget() {
	_ = os.Remove(store.Path)
}
