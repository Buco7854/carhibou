import glob
import re
import time

import serial

from agent.vehicle_agent.models import CANFrame


class AdapterError(Exception):
    pass


def discover_obdlink() -> list[str]:
    stable = sorted(
        glob.glob("/dev/serial/by-id/*OBDLink*") + glob.glob("/dev/serial/by-id/*FTDI*")
    )
    if stable:
        return stable
    return sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))


def parse_can_frame(line: str, timestamp: float | None = None) -> CANFrame:
    cleaned = line.strip().replace(":", " ")
    parts = cleaned.split()
    if len(parts) < 2:
        compact = re.fullmatch(r"([0-9A-Fa-f]{3}|[0-9A-Fa-f]{8})([0-9A-Fa-f]+)", cleaned)
        if not compact:
            raise AdapterError(f"unrecognized CAN frame: {line!r}")
        can_id_text, data_text = compact.groups()
        payload = bytes.fromhex(data_text)
    else:
        can_id_text = parts[0]
        remaining = parts[1:]
        if remaining and remaining[0].isdigit() and int(remaining[0]) <= 8:
            declared = int(remaining.pop(0))
        else:
            declared = None
        payload = bytes.fromhex("".join(remaining))
        if declared is not None and declared != len(payload):
            raise AdapterError("CAN data length does not match declared DLC")
    can_id = int(can_id_text, 16)
    if not 0 <= can_id <= 0x1FFFFFFF or len(payload) > 8:
        raise AdapterError("CAN identifier or payload is outside classic CAN bounds")
    return CANFrame(
        timestamp=timestamp if timestamp is not None else time.time(),
        can_id=can_id,
        data=payload,
    )


class OBDLinkSXAdapter:
    def __init__(self, device: str, baudrate: int = 115200, timeout: float = 2):
        self.device = device
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial: serial.Serial | None = None

    def connect(self) -> None:
        self.close()
        self._serial = serial.Serial(self.device, self.baudrate, timeout=self.timeout)
        self.command("ATZ", delay=1)
        self.command("ATE0")
        self.command("ATL0")
        self.command("ATS1")
        self.command("ATH1")

    def close(self) -> None:
        if self._serial:
            self._serial.close()
        self._serial = None

    def command(self, command: str, delay: float = 0) -> list[str]:
        if not self._serial or not self._serial.is_open:
            raise AdapterError("adapter is not connected")
        self._serial.reset_input_buffer()
        self._serial.write((command.strip() + "\r").encode("ascii"))
        self._serial.flush()
        if delay:
            time.sleep(delay)
        raw = self._serial.read_until(b">").decode("ascii", errors="replace")
        lines = [
            line.strip()
            for line in raw.replace(">", "").replace("\r", "\n").splitlines()
            if line.strip() and line.strip() != command
        ]
        if not lines or any(value in {"?", "ERROR", "UNABLE TO CONNECT"} for value in lines):
            raise AdapterError(f"adapter rejected {command}: {lines}")
        return lines

    def identity(self) -> dict[str, str]:
        return {
            "adapter": " ".join(self.command("ATI")),
            "firmware": " ".join(self.command("STI")),
        }

    def select_protocol(self, protocol: str = "6") -> None:
        if not re.fullmatch(r"[0-9A-Ca-c]", protocol):
            raise ValueError("invalid ELM protocol identifier")
        self.command(f"ATSP{protocol.upper()}")

    def query(self, mode: int, pid: int) -> list[str]:
        return self.command(f"{mode:02X}{pid:02X}")

    def monitor(self, seconds: float, filters: list[int] | None = None) -> list[CANFrame]:
        if filters:
            if len(filters) != 1:
                raise AdapterError("v1 adapter filtering accepts one exact CAN ID")
            self.command(f"ATCRA{filters[0]:03X}")
        if not self._serial:
            raise AdapterError("adapter is not connected")
        self._serial.reset_input_buffer()
        self._serial.write(b"STM\r")
        deadline = time.monotonic() + seconds
        frames: list[CANFrame] = []
        while time.monotonic() < deadline:
            line = self._serial.readline().decode("ascii", errors="replace").strip()
            if line and line != "SEARCHING...":
                try:
                    frames.append(parse_can_frame(line))
                except AdapterError:
                    continue
        self._serial.write(b"\r")
        self._serial.read_until(b">")
        return frames
