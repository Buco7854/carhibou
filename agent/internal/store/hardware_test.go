package store

import (
	"os"
	"path/filepath"
	"testing"
)

// The stored answer saves a sweep, which is seconds of waiting per port, so it has
// to be trusted only while the ports it was made against are the ports that exist.
func TestStoredDetectionIsOnlyTrustedWhileTheHardwareMatches(t *testing.T) {
	directory := t.TempDir()
	present := filepath.Join(directory, "ttyUSB0")
	other := filepath.Join(directory, "ttyUSB1")
	for _, path := range []string{present, other} {
		if err := os.WriteFile(path, nil, 0o600); err != nil {
			t.Fatal(err)
		}
	}
	candidates := []string{present, other}
	detection := Detection{GPS: present, OBD: other, Candidates: candidates}

	if !detection.Usable(candidates) {
		t.Fatal("an answer matching the hardware in front of it must be usable")
	}
	if detection.Usable([]string{present}) {
		t.Fatal("a port disappearing must invalidate the answer")
	}
	if detection.Usable([]string{other, present}) {
		t.Fatal("ports enumerating in another order must invalidate the answer")
	}
	if detection.Usable(append(candidates, filepath.Join(directory, "ttyUSB2"))) {
		t.Fatal("a port appearing must invalidate the answer")
	}

	// A named device that has gone away invalidates it even when the candidate
	// list is unchanged, which is what an agent moved to another socket looks like.
	if err := os.Remove(other); err != nil {
		t.Fatal(err)
	}
	if detection.Usable(candidates) {
		t.Fatal("an answer naming a device that no longer exists must not be used")
	}

	// Nothing to compare against is not a match; it is an empty machine.
	if (Detection{}).Usable(nil) {
		t.Fatal("an empty answer must not be usable")
	}
}

func TestForgettingADetectionLeavesNothingToLoad(t *testing.T) {
	store := DetectionStore{Path: filepath.Join(t.TempDir(), "detection.json")}
	if err := store.Save(Detection{GPS: "/dev/ttyUSB1"}); err != nil {
		t.Fatal(err)
	}
	if _, found := store.Load(); !found {
		t.Fatal("expected the saved answer to load")
	}
	store.Forget()
	if _, found := store.Load(); found {
		t.Fatal("a forgotten answer must not come back")
	}
	// Forgetting what is not there is how a first run behaves, so it must be quiet.
	store.Forget()
}
