package capture

import (
	"bufio"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/Buco7854/vehinode/agent/internal/model"
)

const Format = "vehinode-can-jsonl"
const Version = 1

type Recorder struct{ output io.Writer }

func NewRecorder(output io.Writer, metadata map[string]any) (*Recorder, error) {
	recorder := &Recorder{output: output}
	header := map[string]any{"type": "header", "format": Format, "version": Version, "created_at": time.Now().UTC(), "metadata": metadata}
	return recorder, recorder.write(header)
}

func (recorder *Recorder) Write(frame model.CANFrame) error {
	return recorder.write(map[string]any{"type": "frame", "timestamp": frame.Timestamp, "can_id": fmt.Sprintf("0x%03X", frame.CANID), "data": strings.ToUpper(hex.EncodeToString(frame.Data))})
}

func (recorder *Recorder) write(value any) error {
	content, err := json.Marshal(value)
	if err != nil {
		return err
	}
	content = append(content, '\n')
	_, err = recorder.output.Write(content)
	return err
}

type Capture struct {
	Metadata map[string]any
	Frames   []model.CANFrame
}

func Read(path string) (Capture, error) {
	file, err := os.Open(path)
	if err != nil {
		return Capture{}, err
	}
	defer file.Close()
	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 4096), 1024*1024)
	if !scanner.Scan() {
		return Capture{}, fmt.Errorf("capture header is missing")
	}
	var header struct {
		Format   string         `json:"format"`
		Version  int            `json:"version"`
		Metadata map[string]any `json:"metadata"`
	}
	if err := json.Unmarshal(scanner.Bytes(), &header); err != nil || header.Format != Format || header.Version != Version {
		return Capture{}, fmt.Errorf("unsupported capture format or version")
	}
	result := Capture{Metadata: header.Metadata}
	line := 1
	for scanner.Scan() {
		line++
		var row struct {
			Type      string  `json:"type"`
			Timestamp float64 `json:"timestamp"`
			CANID     string  `json:"can_id"`
			Data      string  `json:"data"`
		}
		if err := json.Unmarshal(scanner.Bytes(), &row); err != nil {
			return Capture{}, fmt.Errorf("invalid frame at line %d: %w", line, err)
		}
		if row.Type != "frame" {
			continue
		}
		id, err := strconv.ParseInt(strings.TrimPrefix(row.CANID, "0x"), 16, 32)
		if err != nil {
			return Capture{}, fmt.Errorf("invalid frame at line %d", line)
		}
		data, err := hex.DecodeString(row.Data)
		if err != nil || len(data) > 8 {
			return Capture{}, fmt.Errorf("invalid frame at line %d", line)
		}
		result.Frames = append(result.Frames, model.CANFrame{Timestamp: row.Timestamp, CANID: int(id), Data: data})
	}
	return result, scanner.Err()
}
