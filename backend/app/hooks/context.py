import io
import math
from collections.abc import Iterator, MutableMapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType, SimpleNamespace
from typing import Any

import httpx


def _object(value: Any) -> Any:
    if isinstance(value, dict):
        return SimpleNamespace(**{key: _object(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_object(item) for item in value)
    return value


def _datetime(value: object) -> object:
    if not isinstance(value, str):
        return value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value


class HookStateMapping(MutableMapping[str, Any]):
    def __init__(self, values: dict[str, Any]):
        self._values = dict(values)

    def __getitem__(self, key: str) -> Any:
        return self._values[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._values[key] = value

    def __delitem__(self, key: str) -> None:
        del self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def snapshot(self) -> dict[str, Any]:
        return dict(self._values)


class CapturedLog:
    def __init__(self, records: list[dict[str, object]]):
        self._records = records

    def _write(self, level: str, message: object, **fields: object) -> None:
        self._records.append(
            {
                "timestamp": datetime.now().astimezone().isoformat(),
                "level": level,
                "message": str(message),
                "fields": fields,
            }
        )

    def info(self, message: object, **fields: object) -> None:
        self._write("info", message, **fields)

    def warning(self, message: object, **fields: object) -> None:
        self._write("warning", message, **fields)

    def error(self, message: object, **fields: object) -> None:
        self._write("error", message, **fields)


@dataclass(frozen=True)
class HookHTTPResponse:
    status_code: int
    headers: MappingProxyType[str, str]
    text: str

    def json(self) -> Any:
        import json

        return json.loads(self.text)


class HookHTTP:
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str | int | float | bool | None] | None = None,
        json: object | None = None,
        text: str | None = None,
        timeout: float = 10,
    ) -> HookHTTPResponse:
        if json is not None and text is not None:
            raise ValueError("provide either json or text, not both")
        response = httpx.request(
            method,
            url,
            headers=headers,
            params=params,
            json=json,
            content=text,
            timeout=min(max(timeout, 0.1), 60),
            follow_redirects=False,
        )
        return HookHTTPResponse(
            status_code=response.status_code,
            headers=MappingProxyType(dict(response.headers)),
            text=response.text[:1_000_000],
        )

    def get(self, url: str, **kwargs: Any) -> HookHTTPResponse:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> HookHTTPResponse:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> HookHTTPResponse:
        return self.request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> HookHTTPResponse:
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> HookHTTPResponse:
        return self.request("DELETE", url, **kwargs)


class Geometry:
    @staticmethod
    def distance_meters(
        latitude: float,
        longitude: float,
        other_latitude: float,
        other_longitude: float,
    ) -> float:
        radius = 6_371_008.8
        lat1, lat2 = math.radians(latitude), math.radians(other_latitude)
        delta_lat = lat2 - lat1
        delta_lon = math.radians(other_longitude - longitude)
        a = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
        )
        return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    @classmethod
    def within_radius(
        cls,
        latitude: float,
        longitude: float,
        center_latitude: float,
        center_longitude: float,
        radius_meters: float,
    ) -> bool:
        return (
            cls.distance_meters(latitude, longitude, center_latitude, center_longitude)
            <= radius_meters
        )


class CappedWriter(io.TextIOBase):
    def __init__(self, limit: int):
        self.limit = limit
        self.value = ""
        self.truncated = False

    def write(self, value: str) -> int:
        remaining = max(0, self.limit - len(self.value.encode()))
        encoded = value.encode()
        if len(encoded) > remaining:
            self.value += encoded[:remaining].decode(errors="replace")
            self.truncated = True
        else:
            self.value += value
        return len(value)

    def writable(self) -> bool:
        return True


def _sample(raw: dict[str, Any]) -> Any:
    sample = dict(raw)
    sample["recorded_at"] = _datetime(sample.get("recorded_at"))
    sample["metrics"] = MappingProxyType(sample.get("metrics", {}))
    sample["agent"] = MappingProxyType(sample.get("agent", {}))
    return _object(sample)


class HookContext:
    def __init__(self, data: dict[str, Any], records: list[dict[str, object]]):
        self.sdk_version = int(data.get("sdk_version", 1))
        event = dict(data["event"])
        event["payload"] = MappingProxyType(event.get("payload", {}))
        event["occurred_at"] = _datetime(event.get("occurred_at"))
        self.event = _object(event)
        raw_batch = data.get("telemetry_batch") or [data["telemetry"]]
        # Oldest first, so the batch reads like a timeline and [-1] is the newest sample.
        self.telemetry_batch = tuple(_sample(row) for row in raw_batch)
        self.telemetry = self.telemetry_batch[-1]
        vehicle = dict(data["vehicle"])
        vehicle_state = dict(vehicle.get("state", {}))
        vehicle_state["metrics"] = MappingProxyType(vehicle_state.get("metrics", {}))
        vehicle_state["agent"] = MappingProxyType(vehicle_state.get("agent", {}))
        vehicle_state["updated_at"] = _datetime(vehicle_state.get("updated_at"))
        vehicle["state"] = vehicle_state
        self.vehicle = _object(vehicle)
        self.agent = _object(data["agent"])
        self.state = HookStateMapping(data.get("state", {}))
        self.secrets = MappingProxyType(data.get("secrets", {}))
        self.dry_run = bool(data.get("dry_run", False))
        self.http = HookHTTP()
        self.geo = Geometry()
        self.log = CapturedLog(records)
