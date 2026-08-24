import json
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from agent.vehicle_agent.models import CANFrame
from agent.vehicle_agent.providers.obdlink import parse_can_frame

CAPTURE_FORMAT = "vehinode-can-jsonl"
CAPTURE_VERSION = 1


class CaptureError(ValueError):
    pass


class CANRecorder:
    def __init__(self, output: TextIO, metadata: dict[str, object]):
        self.output = output
        self.output.write(
            json.dumps(
                {
                    "type": "header",
                    "format": CAPTURE_FORMAT,
                    "version": CAPTURE_VERSION,
                    "created_at": datetime.now(UTC).isoformat(),
                    "metadata": metadata,
                }
            )
            + "\n"
        )

    def write(self, frame: CANFrame) -> None:
        self.output.write(json.dumps(frame.as_dict()) + "\n")
        self.output.flush()


def replay_capture(path: str | Path) -> Iterator[tuple[dict[str, Any], CANFrame]]:
    with Path(path).open() as source:
        first = source.readline()
        try:
            header = json.loads(first)
        except json.JSONDecodeError as exc:
            raise CaptureError("capture header is invalid JSON") from exc
        if header.get("format") != CAPTURE_FORMAT or header.get("version") != CAPTURE_VERSION:
            raise CaptureError("unsupported capture format or version")
        metadata = header.get("metadata", {})
        for number, line in enumerate(source, 2):
            try:
                row = json.loads(line)
                if row.get("type") != "frame":
                    continue
                frame = parse_can_frame(
                    f"{row['can_id']} {row['data']}", timestamp=float(row["timestamp"])
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise CaptureError(f"invalid frame at line {number}") from exc
            yield metadata, frame


def record_frames(output: TextIO, frames: Iterable[CANFrame], metadata: dict[str, object]) -> int:
    recorder = CANRecorder(output, metadata)
    count = 0
    for frame in frames:
        recorder.write(frame)
        count += 1
    return count
