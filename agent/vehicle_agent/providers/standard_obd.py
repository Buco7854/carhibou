from collections.abc import Callable

from agent.vehicle_agent.providers.obdlink import AdapterError, OBDLinkSXAdapter


def _a(data: bytes) -> int:
    if not data:
        raise ValueError("OBD response has no data bytes")
    return data[0]


def _ab(data: bytes) -> int:
    if len(data) < 2:
        raise ValueError("OBD response requires two data bytes")
    return data[0] * 256 + data[1]


PID_DECODERS: dict[int, tuple[str, Callable[[bytes], float], str]] = {
    0x04: ("engine.load", lambda data: _a(data) * 100 / 255, "%"),
    0x05: ("engine.coolant_temperature", lambda data: _a(data) - 40, "°C"),
    0x0C: ("engine.rpm", lambda data: _ab(data) / 4, "rpm"),
    0x0D: ("vehicle.speed", lambda data: float(_a(data)), "km/h"),
    0x0F: ("engine.intake_temperature", lambda data: _a(data) - 40, "°C"),
    0x10: ("engine.maf", lambda data: _ab(data) / 100, "g/s"),
    0x11: ("engine.throttle", lambda data: _a(data) * 100 / 255, "%"),
    0x2F: ("fuel.level", lambda data: _a(data) * 100 / 255, "%"),
    # Control module voltage is the vehicle's reading of the same accessory rail
    # the adapter measures with ATRV, so it carries the same canonical key.
    0x42: ("battery.aux_voltage", lambda data: _ab(data) / 1000, "V"),
    # The only standard route to hybrid/EV pack charge, and unverified against a
    # car: few vehicles answer it, and one that does not simply returns no data.
    # A vehicle profile remains the accurate source wherever one exists.
    0x5B: ("battery.soc", lambda data: _a(data) * 100 / 255, "%"),
}


def parse_obd_response(mode: int, pid: int, lines: list[str]) -> bytes | None:
    expected = bytes((mode + 0x40, pid))
    for line in lines:
        try:
            parts = line.split()
            if parts and len(parts[0]) in {3, 8}:
                parts.pop(0)  # CAN header emitted when ATH1 is enabled
            if parts and len(parts[0]) == 2 and int(parts[0], 16) <= 8:
                parts.pop(0)  # ISO-TP single-frame length
            raw = bytes.fromhex("".join(parts))
        except ValueError:
            continue
        for offset in range(max(0, len(raw) - 1)):
            if raw[offset : offset + 2] == expected:
                return raw[offset + 2 :]
    return None


def decode_standard_pid(pid: int, data: bytes) -> tuple[str, float, str] | None:
    definition = PID_DECODERS.get(pid)
    if not definition:
        return None
    name, decoder, unit = definition
    return name, decoder(data), unit


def _line_payload(line: str) -> bytes:
    parts = line.replace(":", " ").split()
    if parts and len(parts[0]) in {3, 8}:
        parts.pop(0)
    return bytes.fromhex("".join(parts))


def parse_vin_response(lines: list[str]) -> str | None:
    payload = bytearray()
    for line in lines:
        try:
            raw = _line_payload(line)
        except ValueError:
            continue
        if not raw:
            continue
        pci = raw[0]
        if pci >> 4 == 1:
            chunk = raw[2:]
        elif pci >> 4 == 2:
            chunk = raw[1:]
        else:
            chunk = raw[1:] if pci <= 8 else raw
        marker = chunk.find(bytes((0x49, 0x02)))
        if marker >= 0:
            chunk = chunk[marker + 2 :]
            if chunk and chunk[0] in {0x01, 0x02, 0x03}:
                chunk = chunk[1:]
        payload.extend(chunk)
    vin = bytes(value for value in payload if 32 <= value <= 126).decode("ascii", errors="ignore")
    return vin[:17] if len(vin) >= 17 else None


def parse_dtc_response(lines: list[str]) -> list[str]:
    codes: list[str] = []
    families = "PCBU"
    for line in lines:
        try:
            raw = _line_payload(line)
        except ValueError:
            continue
        marker = raw.find(bytes((0x43,)))
        if marker < 0:
            continue
        data = raw[marker + 1 :]
        for offset in range(0, len(data) - 1, 2):
            first, second = data[offset], data[offset + 1]
            if first == 0 and second == 0:
                continue
            codes.append(f"{families[first >> 6]}{(first >> 4) & 3:X}{first & 15:X}{second:02X}")
    return codes


class StandardOBDProvider:
    def __init__(self, adapter: OBDLinkSXAdapter):
        self.adapter = adapter
        self.connected = False

    def read_metrics(self) -> dict[str, object]:
        if not self.connected:
            try:
                self.adapter.connect()
                self.adapter.select_protocol("0")
                self.connected = True
            except AdapterError:
                return {}
        metrics: dict[str, object] = {}
        try:
            for pid in PID_DECODERS:
                raw = parse_obd_response(1, pid, self.adapter.query(1, pid))
                decoded = decode_standard_pid(pid, raw) if raw is not None else None
                if decoded:
                    metrics[decoded[0]] = round(decoded[1], 3)
        except (AdapterError, OSError):
            self.adapter.close()
            self.connected = False
        return metrics
