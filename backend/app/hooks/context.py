import io
import math
from collections.abc import Iterator, MutableMapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any

import httpx
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from backend.app.common import model_registry  # noqa: F401
from backend.app.common.time import as_utc


class ReadOnlyObject:
    __slots__ = ("_values",)

    def __init__(self, values: dict[str, Any]):
        object.__setattr__(self, "_values", MappingProxyType(values))

    def __getattr__(self, key: str) -> Any:
        try:
            return self._values[key]
        except KeyError as exc:
            raise AttributeError(key) from exc

    def __setattr__(self, key: str, value: Any) -> None:
        del key, value
        raise TypeError("hook telemetry values are read-only")

    def __repr__(self) -> str:
        return f"ReadOnlyObject({dict(self._values)!r})"


def _object(value: Any) -> Any:
    if isinstance(value, dict):
        return ReadOnlyObject({key: _object(item) for key, item in value.items()})
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


class HookHTTPError(RuntimeError):
    """A request that never reached a server, said in one line.

    httpx reports these through its own layers, so an author who pointed at the
    wrong port read sixty lines of transport internals to learn that nothing had
    answered. The original is chained, so the detail is still in the traceback
    tail for anyone who wants it.
    """


def _endpoint(method: str, url: str) -> str:
    """Name the request without repeating anything secret.

    Only the scheme, host and port. A path carries record identifiers, a query
    carries tokens, and userinfo carries credentials outright, so the message is
    built from the three parts that locate a server and none of the parts that
    authenticate to it.
    """

    try:
        parsed = httpx.URL(url)
        endpoint = f"{parsed.scheme}://{parsed.host}"
        if parsed.port is not None:
            endpoint = f"{endpoint}:{parsed.port}"
    except (httpx.InvalidURL, UnicodeError, ValueError):
        return method.upper()
    return f"{method.upper()} {endpoint}"


def _hint(error: httpx.TransportError) -> str:
    """Say what a bare disconnect usually means.

    A server that accepts the connection and then closes it without answering is
    almost always speaking something other than HTTP on that port, which is a
    configuration mistake rather than an outage and is worth naming.
    """

    if isinstance(error, httpx.RemoteProtocolError) and "disconnect" in str(error).lower():
        return " - this port may not speak HTTP (Traccar's OsmAnd HTTP port is 5055 by default)"
    return ""


def _one_line(error: Exception) -> str:
    detail = " ".join(str(error).split()).rstrip(".")
    if not detail:
        return type(error).__name__
    return detail[0].lower() + detail[1:]


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
        seconds = min(max(timeout, 0.1), 60)
        try:
            response = httpx.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json,
                content=text,
                timeout=seconds,
                follow_redirects=False,
            )
        except httpx.TimeoutException as exc:
            raise HookHTTPError(f"{_endpoint(method, url)} timed out after {seconds:g}s") from exc
        except httpx.TransportError as exc:
            raise HookHTTPError(
                f"{_endpoint(method, url)} failed: {_one_line(exc)}{_hint(exc)}"
            ) from exc
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


def _state(raw: dict[str, Any]) -> Any:
    readings = {
        key: _object({**value, "observed_at": _datetime(value.get("observed_at"))})
        for key, value in raw.get("readings", {}).items()
    }
    position = raw.get("position")
    if position:
        position = _object({**position, "observed_at": _datetime(position.get("observed_at"))})
    return ReadOnlyObject(
        {
            "updated_at": _datetime(raw.get("updated_at")),
            "online": raw.get("online"),
            "readings": MappingProxyType(readings),
            "position": position,
            "agent": MappingProxyType(dict(raw.get("agent", {}))),
        }
    )


class HookTelemetry:
    def __init__(self, data: dict[str, Any], database_url: str):
        self.vehicle_id = str(data["vehicle_id"])
        self.triggering = tuple(
            _object({**row, "observed_at": _datetime(row.get("observed_at"))})
            for row in data.get("triggering", [])
        )
        self.current = _state(data.get("current", {}))
        self._engine = create_engine(database_url)

    @contextmanager
    def _read_session(self) -> Iterator[Session]:
        with Session(self._engine) as db:
            dialect = db.get_bind().dialect.name
            if dialect == "postgresql":
                db.execute(text("SET TRANSACTION READ ONLY"))
            elif dialect == "sqlite":
                db.execute(text("PRAGMA query_only = ON"))
            yield db
            db.rollback()

    def state_at(self, at: datetime) -> Any:
        from backend.app.history.reconstruction import state_at_time

        if at.tzinfo is None:
            raise ValueError("state_at requires a timezone-aware timestamp")
        with self._read_session() as db:
            return _state(state_at_time(db, self.vehicle_id, at))

    def history(
        self,
        start: datetime,
        end: datetime,
        *,
        keys: Sequence[str] | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> tuple[Any, ...]:
        from backend.app.connectors.models import Connector
        from backend.app.telemetry.models import (
            TelemetryObservation,
            TelemetryPositionObservation,
        )

        if start.tzinfo is None or end.tzinfo is None or start >= end:
            raise ValueError("history requires an ordered timezone-aware range")
        if limit < 1 or limit > 1000 or offset < 0:
            raise ValueError("history limit must be 1..1000 and offset must be non-negative")
        with self._read_session() as db:
            metric_query = select(TelemetryObservation).where(
                TelemetryObservation.vehicle_id == self.vehicle_id,
                TelemetryObservation.observed_at >= start,
                TelemetryObservation.observed_at < end,
            )
            selected_keys = set(keys or ())
            if selected_keys:
                metric_query = metric_query.where(
                    TelemetryObservation.metric_key.in_(selected_keys - {"position"})
                )
            metric_rows = list(
                db.scalars(
                    metric_query.order_by(
                        TelemetryObservation.observed_at,
                        TelemetryObservation.id,
                    ).limit(limit + offset)
                )
            )
            position_rows = []
            if not selected_keys or "position" in selected_keys:
                position_rows = list(
                    db.scalars(
                        select(TelemetryPositionObservation)
                        .where(
                            TelemetryPositionObservation.vehicle_id == self.vehicle_id,
                            TelemetryPositionObservation.observed_at >= start,
                            TelemetryPositionObservation.observed_at < end,
                        )
                        .order_by(TelemetryPositionObservation.observed_at)
                        .limit(limit + offset)
                    )
                )
            connector_ids = set(
                db.scalars(
                    select(Connector.id).where(
                        Connector.id.in_(
                            {row.source_id for row in metric_rows}
                            | {row.source_id for row in position_rows}
                        )
                    )
                )
            )
            values: list[dict[str, Any]] = [
                {
                    "telemetry_id": row.telemetry_id,
                    "key": row.metric_key,
                    "value": row.value,
                    "observed_at": as_utc(row.observed_at),
                    "source_id": row.source_id,
                    "source_kind": "connector" if row.source_id in connector_ids else "agent",
                    "channel": row.channel,
                    "method": row.method,
                }
                for row in metric_rows
            ]
            values.extend(
                {
                    "telemetry_id": row.telemetry_id,
                    "key": "position",
                    "value": row.value,
                    "observed_at": as_utc(row.observed_at),
                    "source_id": row.source_id,
                    "source_kind": "connector" if row.source_id in connector_ids else "agent",
                    "channel": row.channel,
                    "method": row.method,
                }
                for row in position_rows
            )
            values.sort(key=lambda row: (row["observed_at"], row["telemetry_id"], row["key"]))
            return tuple(_object(row) for row in values[offset : offset + limit])


class HookContext:
    def __init__(self, data: dict[str, Any], records: list[dict[str, object]]):
        self.sdk_version = int(data.get("sdk_version", 1))
        event = dict(data["event"])
        event["payload"] = MappingProxyType(event.get("payload", {}))
        event["occurred_at"] = _datetime(event.get("occurred_at"))
        self.event = _object(event)
        self.telemetry = HookTelemetry(data["telemetry_context"], data["database_url"])
        self.vehicle = _object(data["vehicle"])
        self.agent = _object(data["agent"])
        self.state = HookStateMapping(data.get("state", {}))
        self.secrets = MappingProxyType(data.get("secrets", {}))
        self.dry_run = bool(data.get("dry_run", False))
        self.http = HookHTTP()
        self.geo = Geometry()
        self.log = CapturedLog(records)
