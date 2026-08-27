from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from agent.vehicle_agent.models import CANFrame

INTEGER_TYPES: dict[str, tuple[int, bool]] = {
    "uint8": (1, False),
    "uint16": (2, False),
    "uint32": (4, False),
    "int8": (1, True),
    "int16": (2, True),
    "int32": (4, True),
}


class ProfileError(ValueError):
    pass


@dataclass(frozen=True)
class DecodedSignal:
    name: str
    value: object
    unit: str | None


class VehicleProfileDecoder:
    def __init__(self, profile: dict[str, Any]):
        self.profile = profile
        if not isinstance(profile.get("id"), str) or not isinstance(profile.get("signals"), list):
            raise ProfileError("profile requires string id and signals list")
        self.by_can_id: dict[int, list[dict[str, Any]]] = {}
        for signal in profile["signals"]:
            self._validate_signal(signal)
            can_id = signal["source"]["can_id"]
            self.by_can_id.setdefault(can_id, []).append(signal)
        self.computed = profile.get("computed_metrics", [])

    @classmethod
    def from_path(cls, path: str | Path) -> "VehicleProfileDecoder":
        loaded = yaml.safe_load(Path(path).read_text())
        if not isinstance(loaded, dict):
            raise ProfileError("profile root must be an object")
        return cls(loaded)

    @staticmethod
    def _validate_signal(signal: dict[str, Any]) -> None:
        required = {"name", "source", "decoder"}
        if not required.issubset(signal):
            raise ProfileError(f"signal is missing keys: {required - set(signal)}")
        source = signal["source"]
        if source.get("type") != "can" or not isinstance(source.get("can_id"), int):
            raise ProfileError("v1 profile signal source must be a numeric CAN ID")
        data_type = signal["decoder"].get("data_type")
        if data_type not in {*INTEGER_TYPES, "bytes", "boolean"}:
            raise ProfileError(f"unsupported decoder type: {data_type}")

    @staticmethod
    def _raw_value(data: bytes, decoder: dict[str, Any]) -> int | bool:
        offset = int(decoder.get("byte_offset", 0))
        data_type = decoder["data_type"]
        if data_type == "boolean":
            if offset >= len(data):
                raise ProfileError("boolean offset exceeds CAN payload")
            bit = int(decoder.get("bit", 0))
            if not 0 <= bit <= 7:
                raise ProfileError("boolean bit must be between 0 and 7")
            return bool(data[offset] & (1 << bit))
        if data_type == "bytes":
            length = int(decoder.get("length", 1))
            signed = bool(decoder.get("signed", False))
        else:
            length, signed = INTEGER_TYPES[data_type]
        chunk = data[offset : offset + length]
        if len(chunk) != length:
            raise ProfileError("decoder slice exceeds CAN payload")
        endianness = decoder.get("endianness", "big")
        if endianness not in {"big", "little"}:
            raise ProfileError("endianness must be big or little")
        value = int.from_bytes(chunk, byteorder=endianness, signed=signed)
        if "bit_mask" in decoder:
            mask = decoder["bit_mask"]
            mask = int(mask, 0) if isinstance(mask, str) else int(mask)
            value &= mask
        if "shift" in decoder:
            value >>= int(decoder["shift"])
        return value

    @classmethod
    def _decode(cls, signal: dict[str, Any], data: bytes) -> object:
        decoder = signal["decoder"]
        raw = cls._raw_value(data, decoder)
        if isinstance(raw, bool):
            return raw
        enum = decoder.get("enum")
        if enum is not None:
            return enum.get(raw, enum.get(str(raw), f"unknown:{raw}"))
        value = raw * float(decoder.get("scale", 1)) + float(decoder.get("offset", 0))
        if signal.get("minimum") is not None and value < float(signal["minimum"]):
            raise ProfileError(f"{signal['name']} is below its sanity minimum")
        if signal.get("maximum") is not None and value > float(signal["maximum"]):
            raise ProfileError(f"{signal['name']} is above its sanity maximum")
        return value

    def decode(
        self, frame: CANFrame, metrics: dict[str, object] | None = None
    ) -> list[DecodedSignal]:
        decoded: list[DecodedSignal] = []
        current = dict(metrics or {})
        for signal in self.by_can_id.get(frame.can_id, []):
            try:
                value = self._decode(signal, frame.data)
            except ProfileError:
                continue
            current[signal["name"]] = value
            decoded.append(DecodedSignal(signal["name"], value, signal.get("unit")))
        for computed in self.computed:
            inputs = computed.get("inputs", [])
            if computed.get("operation") == "multiply" and all(name in current for name in inputs):
                left, right = current[inputs[0]], current[inputs[1]]
                if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
                    continue
                value = float(left) * float(right) * float(computed.get("scale", 1))
                current[computed["name"]] = value
                decoded.append(DecodedSignal(computed["name"], value, computed.get("unit")))
        return decoded
