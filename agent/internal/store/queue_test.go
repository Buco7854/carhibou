package store

import (
	"path/filepath"
	"testing"

	"github.com/Buco7854/vehinode/agent/internal/model"
)

func TestQueueSurvivesRestartAndAcknowledgesIDs(t *testing.T) {
	path := filepath.Join(t.TempDir(), "queue.sqlite3")
	queue, err := OpenQueue(path)
	if err != nil {
		t.Fatal(err)
	}
	first := model.NewSample(1, nil, map[string]any{"battery.soc": 70}, nil)
	second := model.NewSample(2, nil, map[string]any{"battery.soc": 69}, nil)
	if err := queue.Enqueue(first); err != nil {
		t.Fatal(err)
	}
	if err := queue.Enqueue(second); err != nil {
		t.Fatal(err)
	}
	queue.Close()

	queue, err = OpenQueue(path)
	if err != nil {
		t.Fatal(err)
	}
	defer queue.Close()
	pending, err := queue.Pending(500)
	if err != nil {
		t.Fatal(err)
	}
	if len(pending) != 2 || pending[0].ID != first.ID || pending[1].ID != second.ID {
		t.Fatalf("unexpected pending rows: %#v", pending)
	}
	deleted, err := queue.Acknowledge([]string{first.ID})
	if err != nil || deleted != 1 {
		t.Fatalf("acknowledge = %d, %v", deleted, err)
	}
	depth, err := queue.Depth()
	if err != nil || depth != 1 {
		t.Fatalf("depth = %d, %v", depth, err)
	}
}
