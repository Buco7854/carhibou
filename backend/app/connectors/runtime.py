import logging
import ssl
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.agents.models import Agent
from backend.app.common.time import utcnow
from backend.app.connectors.models import Connector
from backend.app.connectors.schemas import MqttConfig
from backend.app.connectors.services import connector_password
from backend.app.telemetry.schemas import Position, TelemetryBatch, TelemetrySample
from backend.app.telemetry.services import ingest_batch
from backend.app.vehicle_profiles.mapping import MappingEngine
from backend.app.vehicle_profiles.schemas import MappingProfileDefinition
from backend.app.vehicle_profiles.services import mapping_profile_definition

logger = logging.getLogger(__name__)
STATUS_WRITE_SECONDS = 3.0
MAX_BACKOFF_SECONDS = 60.0


@dataclass(frozen=True)
class ConnectorDefinition:
    id: str
    config_version: int
    config: MqttConfig
    mapping_profile: MappingProfileDefinition
    password: str | None


class ManagedSession(Protocol):
    definition: ConnectorDefinition

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def join(self, timeout: float | None = None) -> None: ...


def _mqtt_client() -> mqtt.Client:
    return mqtt.Client(CallbackAPIVersion.VERSION2, client_id=f"carhibou-{uuid4()}")


class MqttConnectorSession:
    def __init__(
        self,
        definition: ConnectorDefinition,
        session_factory: sessionmaker[Session],
        *,
        client_factory: Callable[[], Any] = _mqtt_client,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.definition = definition
        self._session_factory = session_factory
        self._client_factory = client_factory
        self._mapping = MappingEngine(definition.mapping_profile)
        self._monotonic = monotonic
        self._stop = threading.Event()
        self._disconnected = threading.Event()
        self._connected = threading.Event()
        self._thread = threading.Thread(
            target=self.run, name=f"connector-{definition.id}", daemon=True
        )
        self._boot_id = uuid4()
        self._sequence = 0
        self._metrics: dict[str, float | int | bool | str | None] = {}
        self._position: dict[str, float] = {}
        self._window_started: float | None = None
        self._last_status_write = float("-inf")
        self._mapping_errors = 0
        self._pending_message = False
        self._pending_error: str | None = None

    @property
    def topic_prefix(self) -> str:
        namespace = (
            f"{self.definition.config.namespace}/" if self.definition.config.namespace else ""
        )
        return f"teslamate/{namespace}cars/{self.definition.config.car_id}/"

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout)

    def _write_status(
        self,
        *,
        status: str | None = None,
        error: str | None = None,
        connected: bool = False,
        message: bool = False,
        force: bool = False,
    ) -> None:
        now_mono = self._monotonic()
        if not force and now_mono - self._last_status_write < STATUS_WRITE_SECONDS:
            return
        now = utcnow()
        with self._session_factory() as db:
            connector = db.get(Connector, self.definition.id)
            if not connector:
                return
            if not connector.enabled:
                connector.status = "disabled"
                connector.last_error = ""
                db.commit()
                self._last_status_write = now_mono
                return
            if status is not None:
                connector.status = status
            if error is not None:
                connector.last_error = error[:4000]
            if connected:
                connector.last_connected_at = now
            if message:
                connector.last_message_at = now
            db.commit()
        self._last_status_write = now_mono

    def handle_message(self, topic: str, payload: bytes | str) -> None:
        if not topic.startswith(self.topic_prefix):
            return
        key = topic.removeprefix(self.topic_prefix)
        if not key or "/" in key:
            return
        mapped = self._mapping.map(key, payload)
        self._metrics.update(mapped.metrics)
        self._position.update(mapped.position)
        if (mapped.metrics or mapped.position) and self._window_started is None:
            self._window_started = self._monotonic()
        self._record_mapping_notes(mapped.errors)
        self._pending_message = True
        self.flush_status()

    def _record_mapping_notes(self, notes: list[str]) -> None:
        if not notes:
            return
        self._mapping_errors += len(notes)
        self._pending_error = f"{self._mapping_errors} mapping error(s); latest: {notes[-1]}"

    def flush_status(self, *, force: bool = False) -> None:
        if not self._pending_message and self._pending_error is None:
            return
        before = self._last_status_write
        self._write_status(
            error=self._pending_error,
            message=self._pending_message,
            force=force,
        )
        if self._last_status_write != before:
            self._pending_message = False
            self._pending_error = None

    def flush(self, *, force: bool = False) -> bool:
        if self._window_started is None:
            return False
        if (
            not force
            and self._monotonic() - self._window_started < self.definition.config.sample_seconds
        ):
            return False
        position = None
        if "latitude" in self._position and "longitude" in self._position:
            try:
                position = Position(**self._position)
            except ValidationError:
                self._record_mapping_notes(["buffered position failed validation"])
        sample = TelemetrySample(
            id=uuid4(),
            sequence=self._sequence,
            recorded_at=utcnow(),
            position=position,
            metrics=self._metrics,
        )
        with self._session_factory() as db:
            agent = db.get(Agent, self.definition.id)
            connector = db.get(Connector, self.definition.id)
            if not agent or not connector or not connector.enabled:
                self._metrics.clear()
                self._position.clear()
                self._window_started = None
                return False
            ingest_batch(db, agent, TelemetryBatch(boot_id=self._boot_id, samples=[sample]))
            connector.last_sample_at = utcnow()
            db.commit()
        self._sequence += 1
        self._metrics = {}
        self._position = {}
        self._window_started = None
        return True

    def _configure_client(self, client: Any) -> None:
        config = self.definition.config
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        if config.username:
            client.username_pw_set(config.username, self.definition.password)
        if config.tls:
            client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
            client.tls_insecure_set(config.tls_accept_invalid_certs)

    def _on_connect(
        self, client: Any, userdata: object, flags: object, reason_code: Any, properties: object
    ) -> None:
        del userdata, flags, properties
        if int(reason_code) != 0:
            self._disconnected.set()
            return
        self._disconnected.clear()
        self._connected.set()
        client.subscribe(f"{self.topic_prefix}+", qos=1)
        self._write_status(status="connected", error="", connected=True, force=True)

    def _on_disconnect(
        self,
        client: Any,
        userdata: object,
        disconnect_flags: object,
        reason_code: object,
        properties: object,
    ) -> None:
        del client, userdata, disconnect_flags, reason_code, properties
        self._disconnected.set()

    def _on_message(self, client: Any, userdata: object, message: Any) -> None:
        del client, userdata
        self.handle_message(str(message.topic), message.payload)

    def run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            self._boot_id = uuid4()
            self._sequence = 0
            self._connected.clear()
            client = self._client_factory()
            try:
                self._write_status(status="connecting", error="", force=True)
                self._configure_client(client)
                self._disconnected.clear()
                client.connect(
                    self.definition.config.host,
                    self.definition.config.port,
                    keepalive=60,
                )
                while not self._stop.is_set() and not self._disconnected.is_set():
                    result = client.loop(timeout=0.5)
                    if self._connected.is_set():
                        backoff = 1.0
                    self.flush()
                    self.flush_status()
                    if result != mqtt.MQTT_ERR_SUCCESS:
                        raise ConnectionError(f"MQTT loop stopped with code {result}")
                if self._stop.is_set():
                    break
                raise ConnectionError("MQTT connection closed")
            except Exception as exc:
                with suppress(Exception):
                    self.flush(force=True)
                self._write_status(status="error", error=str(exc), force=True)
                logger.warning(
                    "connector MQTT session failed",
                    extra={"connector_id": self.definition.id, "error": str(exc)},
                )
                if self._stop.wait(backoff):
                    break
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
            finally:
                with suppress(Exception):
                    client.disconnect()
        self.flush(force=True)


SessionBuilder = Callable[[ConnectorDefinition, sessionmaker[Session]], ManagedSession]


class ConnectorSupervisor:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        session_builder: SessionBuilder = MqttConnectorSession,
        interval_seconds: float = 2.0,
    ) -> None:
        self._session_factory = session_factory
        self._session_builder = session_builder
        self._interval_seconds = interval_seconds
        self._sessions: dict[str, ManagedSession] = {}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self.run, name="connector-supervisor", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        for session in tuple(self._sessions.values()):
            session.stop()

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout)
        for session in tuple(self._sessions.values()):
            session.join(timeout)

    def _definitions(self) -> dict[str, ConnectorDefinition]:
        definitions: dict[str, ConnectorDefinition] = {}
        with self._session_factory() as db:
            rows = db.scalars(select(Connector).where(Connector.enabled.is_(True)))
            for connector in rows:
                try:
                    config = MqttConfig.model_validate(connector.config)
                    profile = mapping_profile_definition(db, connector.mapping_profile)
                    if not profile:
                        raise ValueError("mapping profile is not available")
                    password = connector_password(connector)
                except Exception as exc:
                    connector.status = "error"
                    connector.last_error = f"invalid stored connector configuration: {exc}"[:4000]
                    continue
                definitions[connector.id] = ConnectorDefinition(
                    id=connector.id,
                    config_version=connector.config_version,
                    config=config,
                    mapping_profile=profile,
                    password=password,
                )
            db.commit()
        return definitions

    def reconcile(self) -> None:
        definitions = self._definitions()
        for connector_id, session in tuple(self._sessions.items()):
            definition = definitions.get(connector_id)
            if not definition or definition.config_version != session.definition.config_version:
                session.stop()
                session.join(5)
                del self._sessions[connector_id]
        for connector_id, definition in definitions.items():
            if connector_id in self._sessions:
                continue
            session = self._session_builder(definition, self._session_factory)
            self._sessions[connector_id] = session
            session.start()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                self.reconcile()
            except Exception:
                logger.exception("connector supervisor reconciliation failed")
            self._stop.wait(self._interval_seconds)
        for session in tuple(self._sessions.values()):
            session.stop()
        for session in tuple(self._sessions.values()):
            session.join(5)
