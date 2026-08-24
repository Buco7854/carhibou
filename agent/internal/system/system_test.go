package system

import "testing"

func TestReleaseArtifactName(t *testing.T) {
	if value := ArtifactName("0.1.0", "linux-armv6"); value != "vehinode-agent-0.1.0-linux-armv6" {
		t.Fatal(value)
	}
}
