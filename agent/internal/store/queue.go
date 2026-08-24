package store

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"

	"github.com/Buco7854/vehinode/agent/internal/model"
	_ "modernc.org/sqlite"
)

type Queue struct{ db *sql.DB }

func OpenQueue(path string) (*Queue, error) {
	if err := os.MkdirAll(filepath.Dir(path), 0o750); err != nil {
		return nil, err
	}
	database, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, err
	}
	database.SetMaxOpenConns(1)
	for _, statement := range []string{
		"PRAGMA journal_mode=WAL", "PRAGMA synchronous=FULL", "PRAGMA busy_timeout=5000",
		`CREATE TABLE IF NOT EXISTS samples (
            id TEXT PRIMARY KEY,
            sequence INTEGER NOT NULL,
            recorded_at TEXT NOT NULL,
            payload TEXT NOT NULL,
            queued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )`,
	} {
		if _, err := database.Exec(statement); err != nil {
			database.Close()
			return nil, err
		}
	}
	return &Queue{db: database}, nil
}

func (queue *Queue) Enqueue(sample model.Sample) error {
	payload, err := json.Marshal(sample)
	if err != nil {
		return err
	}
	_, err = queue.db.Exec("INSERT OR IGNORE INTO samples (id, sequence, recorded_at, payload) VALUES (?, ?, ?, ?)", sample.ID, sample.Sequence, sample.RecordedAt.Format("2006-01-02T15:04:05.999999Z07:00"), string(payload))
	return err
}

func (queue *Queue) Pending(limit int) ([]model.Sample, error) {
	rows, err := queue.db.Query("SELECT payload FROM samples ORDER BY sequence, queued_at LIMIT ?", limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	result := []model.Sample{}
	for rows.Next() {
		var payload string
		if err := rows.Scan(&payload); err != nil {
			return nil, err
		}
		var sample model.Sample
		if err := json.Unmarshal([]byte(payload), &sample); err != nil {
			return nil, fmt.Errorf("invalid queued sample: %w", err)
		}
		result = append(result, sample)
	}
	return result, rows.Err()
}

func (queue *Queue) Acknowledge(ids []string) (int64, error) {
	if len(ids) == 0 {
		return 0, nil
	}
	transaction, err := queue.db.Begin()
	if err != nil {
		return 0, err
	}
	statement, err := transaction.Prepare("DELETE FROM samples WHERE id = ?")
	if err != nil {
		transaction.Rollback()
		return 0, err
	}
	defer statement.Close()
	var deleted int64
	for _, id := range ids {
		result, err := statement.Exec(id)
		if err != nil {
			transaction.Rollback()
			return 0, err
		}
		count, _ := result.RowsAffected()
		deleted += count
	}
	if err := transaction.Commit(); err != nil {
		return 0, err
	}
	return deleted, nil
}

func (queue *Queue) Depth() (int, error) {
	var count int
	err := queue.db.QueryRow("SELECT COUNT(*) FROM samples").Scan(&count)
	return count, err
}

func (queue *Queue) LastSequence() (int64, error) {
	var sequence int64
	err := queue.db.QueryRow("SELECT COALESCE(MAX(sequence), 0) FROM samples").Scan(&sequence)
	return sequence, err
}

func (queue *Queue) Close() error { return queue.db.Close() }
