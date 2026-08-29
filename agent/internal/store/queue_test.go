package store

import (
	"database/sql"
	"path/filepath"
	"testing"
	"time"

	"github.com/Buco7854/carhibou/agent/internal/model"
)

func TestQueueSurvivesRestartAndAcknowledgesIDs(t *testing.T) {
	path := filepath.Join(t.TempDir(), "queue.sqlite3")
	queue, err := OpenQueue(path)
	if err != nil {
		t.Fatal(err)
	}
	first := model.NewSample(1, nil, []model.Observation{{Key: "battery.soc", Value: 70, ObservedAt: time.Now().UTC(), Channel: model.ChannelCAN, Method: model.MethodDirect}}, nil)
	second := model.NewSample(2, nil, []model.Observation{{Key: "battery.soc", Value: 69, ObservedAt: time.Now().UTC(), Channel: model.ChannelCAN, Method: model.MethodDirect}}, nil)
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

func TestQueueDropsIncompatibleTelemetryPayloads(t *testing.T) {
	path := filepath.Join(t.TempDir(), "queue.sqlite3")
	database, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatal(err)
	}
	_, err = database.Exec(`CREATE TABLE samples (
        id TEXT PRIMARY KEY,
        sequence INTEGER NOT NULL,
        recorded_at TEXT NOT NULL,
        payload TEXT NOT NULL,
        queued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )`)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := database.Exec(`INSERT INTO samples (id, sequence, recorded_at, payload) VALUES ('old', 1, '2026-01-01T00:00:00Z', '{"metrics":{"battery.soc":70}}')`); err != nil {
		t.Fatal(err)
	}
	if _, err := database.Exec("PRAGMA user_version=1"); err != nil {
		t.Fatal(err)
	}
	database.Close()

	queue, err := OpenQueue(path)
	if err != nil {
		t.Fatal(err)
	}
	defer queue.Close()
	depth, err := queue.Depth()
	if err != nil || depth != 0 {
		t.Fatalf("depth=%d err=%v, incompatible samples must be discarded", depth, err)
	}
}
