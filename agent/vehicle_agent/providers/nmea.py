from datetime import UTC, datetime
from math import hypot
from pathlib import Path

import serial

from agent.vehicle_agent.hardware import gps_candidates
from agent.vehicle_agent.models import PositionFix

KNOTS_TO_KMH = 1.852


class NMEAError(ValueError):
    pass


def _checksum(sentence: str) -> bool:
    if "*" not in sentence:
        return False
    body, expected = sentence.lstrip("$").split("*", 1)
    value = 0
    for character in body:
        value ^= ord(character)
    try:
        return value == int(expected[:2], 16)
    except ValueError:
        return False


def _coordinate(value: str, hemisphere: str) -> float:
    if not value or hemisphere not in {"N", "S", "E", "W"}:
        raise NMEAError("coordinate is incomplete")
    degree_digits = 2 if hemisphere in {"N", "S"} else 3
    degrees = int(value[:degree_digits])
    minutes = float(value[degree_digits:])
    result = degrees + minutes / 60
    if hemisphere in {"S", "W"}:
        result = -result
    return result


def _rmc_datetime(time_value: str, date_value: str) -> datetime | None:
    if len(time_value) < 6 or len(date_value) != 6:
        return None
    microseconds = 0
    if "." in time_value:
        fraction = time_value.split(".", 1)[1]
        microseconds = int((fraction + "000000")[:6])
    year = int(date_value[4:6])
    return datetime(
        (1900 if year >= 80 else 2000) + year,
        int(date_value[2:4]),
        int(date_value[0:2]),
        int(time_value[0:2]),
        int(time_value[2:4]),
        int(time_value[4:6]),
        microseconds,
        tzinfo=UTC,
    )


def parse_nmea(sentence: str) -> PositionFix | None:
    line = sentence.strip()
    if not line.startswith("$") or not _checksum(line):
        raise NMEAError("NMEA checksum is missing or invalid")
    fields = line.split("*", 1)[0].split(",")
    sentence_type = fields[0][-3:]
    if sentence_type == "RMC":
        if len(fields) < 10 or fields[2] != "A":
            return None
        speed = float(fields[7]) * KNOTS_TO_KMH if fields[7] else None
        heading = float(fields[8]) if fields[8] else None
        return PositionFix(
            latitude=_coordinate(fields[3], fields[4]),
            longitude=_coordinate(fields[5], fields[6]),
            speed=speed,
            heading=heading,
            recorded_at=_rmc_datetime(fields[1], fields[9]),
        )
    if sentence_type == "GGA":
        if len(fields) < 10:
            raise NMEAError("GGA sentence is incomplete")
        quality = int(fields[6] or "0")
        if quality <= 0:
            return None
        return PositionFix(
            latitude=_coordinate(fields[2], fields[3]),
            longitude=_coordinate(fields[4], fields[5]),
            altitude=float(fields[9]) if fields[9] else None,
            fix_quality=quality,
            satellites=int(fields[7]) if fields[7] else None,
        )
    return None


def parse_gst_accuracy(sentence: str) -> float | None:
    """Return NMEA GST horizontal one-sigma error in metres when reported."""
    line = sentence.strip()
    if not line.startswith("$") or not _checksum(line):
        raise NMEAError("NMEA checksum is missing or invalid")
    fields = line.split("*", 1)[0].split(",")
    if fields[0][-3:] != "GST":
        return None
    if len(fields) < 8 or not fields[6] or not fields[7]:
        return None
    latitude_sigma = float(fields[6])
    longitude_sigma = float(fields[7])
    return hypot(latitude_sigma, longitude_sigma)


class NMEAAccumulator:
    def __init__(self) -> None:
        self.last_fix: PositionFix | None = None

    def consume(self, sentence: str) -> PositionFix | None:
        accuracy = parse_gst_accuracy(sentence)
        if accuracy is not None and self.last_fix is not None:
            gst_previous = self.last_fix
            self.last_fix = PositionFix(
                latitude=gst_previous.latitude,
                longitude=gst_previous.longitude,
                recorded_at=gst_previous.recorded_at,
                altitude=gst_previous.altitude,
                speed=gst_previous.speed,
                heading=gst_previous.heading,
                accuracy=accuracy,
                fix_quality=gst_previous.fix_quality,
                satellites=gst_previous.satellites,
            )
            return self.last_fix
        fix = parse_nmea(sentence)
        if fix is None:
            return None
        previous = self.last_fix
        if (
            previous
            and abs(previous.latitude - fix.latitude) < 0.001
            and abs(previous.longitude - fix.longitude) < 0.001
        ):
            fix = PositionFix(
                latitude=fix.latitude,
                longitude=fix.longitude,
                recorded_at=fix.recorded_at or previous.recorded_at,
                altitude=fix.altitude if fix.altitude is not None else previous.altitude,
                speed=fix.speed if fix.speed is not None else previous.speed,
                heading=fix.heading if fix.heading is not None else previous.heading,
                accuracy=fix.accuracy if fix.accuracy is not None else previous.accuracy,
                fix_quality=fix.fix_quality or previous.fix_quality,
                satellites=fix.satellites or previous.satellites,
            )
        self.last_fix = fix
        return fix


def discover_sim7600_nmea() -> Path | None:
    candidates = gps_candidates()
    if candidates:
        # Multi-port modems still need gps-info verification and may require explicit selection.
        return Path(candidates[0])
    return None


class SIM7600NMEAProvider:
    def __init__(self, device: str, baudrate: int = 115200, timeout: float = 2):
        self.device = device
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial: serial.Serial | None = None
        self._parser = NMEAAccumulator()

    def _connection(self) -> serial.Serial:
        if not self._serial or not self._serial.is_open:
            self._serial = serial.Serial(self.device, self.baudrate, timeout=self.timeout)
        return self._serial

    def read(self) -> PositionFix | None:
        try:
            line = self._connection().readline().decode("ascii", errors="replace")
            return self._parser.consume(line) if line else None
        except (OSError, serial.SerialException, NMEAError):
            if self._serial:
                self._serial.close()
            self._serial = None
            return None


class NullPositionProvider:
    def read(self) -> PositionFix | None:
        return None
