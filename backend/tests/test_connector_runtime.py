import time
from dataclasses import dataclass
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.connectors.models import Connector
from backend.app.connectors.runtime import (
    ConnectorDefinition,
    ConnectorSupervisor,
    MqttConnectorSession,
)
from backend.app.connectors.schemas import MqttConfig
from backend.app.hooks.models import HookExecution
from backend.app.jobs.models import Job
from backend.app.telemetry.models import Telemetry
from backend.app.vehicle_state.models import VehicleState

CONFIG = MqttConfig(host="broker.test", namespace="fleet", sample_seconds=10)


class Clock:
    value = 0.0

    def __call__(self) -> float:
        return self.value


def _connector(
    registered: tuple[TestClient, str], *, sample_seconds: int = 10
) -> tuple[TestClient, str, dict[str, Any]]:
    client, csrf = registered
    headers = {"X-CSRF-Token": csrf}
    vehicle = client.post("/api/v1/vehicles", headers=headers, json={"name": "MQTT car"}).json()
    response = client.post(
        f"/api/v1/vehicles/{vehicle['id']}/connectors",
        headers=headers,
        json={
            "kind": "teslamate.mqtt",
            "name": "TeslaMate",
            "config": {
                **CONFIG.model_dump(),
                "sample_seconds": sample_seconds,
            },
        },
    )
    assert response.status_code == 201, response.text
    return client, csrf, {**response.json(), "vehicle": vehicle}


def test_snapshot_delta_window_and_end_to_end_pipeline(
    registered: tuple[TestClient, str], db_factory: sessionmaker[Session]
) -> None:
    client, csrf, data = _connector(registered)
    vehicle_id = data["vehicle_id"]
    hook = client.post(
        "/api/v1/hooks",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "Connector hook",
            "enabled": True,
            "vehicle_id": vehicle_id,
            "source": "def handle(event, carhibou):\n    return None",
        },
    )
    assert hook.status_code == 201, hook.text
    clock = Clock()
    definition = ConnectorDefinition(
        id=data["id"],
        config_version=1,
        config=CONFIG,
        password=None,
    )
    session = MqttConnectorSession(definition, db_factory, monotonic=clock)
    prefix = session.topic_prefix
    session.handle_message(f"{prefix}location", b'{"latitude":48.1,"longitude":2.2}')
    session.handle_message(f"{prefix}battery_level", b"72")
    session.handle_message(f"{prefix}inside_temp", b"21.5")
    session.handle_message(f"{prefix}power", b"bad value")
    clock.value = 9
    assert not session.flush()
    clock.value = 10
    assert session.flush()

    with db_factory() as db:
        rows = list(db.scalars(select(Telemetry).order_by(Telemetry.sequence)))
        assert len(rows) == 1
        assert rows[0].metrics == {"battery.soc": 72.0, "teslamate.inside_temp": 21.5}
        assert rows[0].latitude == 48.1
        assert db.scalar(select(Job).where(Job.type == "hook.execute"))
        assert db.scalar(select(HookExecution))

    session.handle_message(f"{prefix}battery_level", b"70")
    clock.value = 19
    assert not session.flush()
    clock.value = 20
    assert session.flush()
    with db_factory() as db:
        rows = list(db.scalars(select(Telemetry).order_by(Telemetry.sequence)))
        assert len(rows) == 2
        assert rows[1].metrics == {"battery.soc": 70.0}
        state = db.get(VehicleState, vehicle_id)
        assert state
        assert state.latest_metrics == {
            "battery.soc": 70.0,
            "teslamate.inside_temp": 21.5,
        }
        assert state.latitude == 48.1

    history = client.get(f"/api/v1/vehicles/{vehicle_id}/history")
    assert history.status_code == 200
    assert "teslamate.inside_temp" in history.json()["available_metrics"]


@dataclass
class FakeManagedSession:
    definition: ConnectorDefinition
    starts: int = 0
    stops: int = 0
    joins: int = 0

    def start(self) -> None:
        self.starts += 1

    def stop(self) -> None:
        self.stops += 1

    def join(self, timeout: float | None = None) -> None:
        del timeout
        self.joins += 1


def test_supervisor_restarts_changes_and_tears_down_disabled_or_deleted(
    registered: tuple[TestClient, str], db_factory: sessionmaker[Session]
) -> None:
    _client, _csrf, data = _connector(registered)
    made: list[FakeManagedSession] = []

    def build(
        definition: ConnectorDefinition, factory: sessionmaker[Session]
    ) -> FakeManagedSession:
        del factory
        session = FakeManagedSession(definition)
        made.append(session)
        return session

    supervisor = ConnectorSupervisor(db_factory, session_builder=build)
    supervisor.reconcile()
    assert len(made) == 1 and made[0].starts == 1
    supervisor.reconcile()
    assert len(made) == 1

    with db_factory() as db:
        connector = db.get(Connector, data["id"])
        assert connector
        connector.config_version += 1
        db.commit()
    supervisor.reconcile()
    assert made[0].stops == made[0].joins == 1
    assert len(made) == 2 and made[1].starts == 1

    with db_factory() as db:
        connector = db.get(Connector, data["id"])
        assert connector
        connector.enabled = False
        connector.status = "disabled"
        db.commit()
    supervisor.reconcile()
    assert made[1].stops == made[1].joins == 1

    with db_factory() as db:
        connector = db.get(Connector, data["id"])
        assert connector
        connector.enabled = True
        db.commit()
    supervisor.reconcile()
    assert len(made) == 3
    with db_factory() as db:
        connector = db.get(Connector, data["id"])
        assert connector
        db.delete(connector)
        db.commit()
    supervisor.reconcile()
    assert made[2].stops == made[2].joins == 1


class FakeClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.on_connect: Any = None
        self.on_disconnect: Any = None
        self.on_message: Any = None
        self.loops = 0

    def username_pw_set(self, username: str, password: str | None) -> None:
        del username, password

    def connect(self, host: str, port: int, keepalive: int) -> None:
        del host, port, keepalive
        if self.fail:
            raise ConnectionError("broker unavailable")

    def loop(self, timeout: float) -> int:
        del timeout
        self.loops += 1
        if self.loops == 1:
            self.on_connect(self, None, None, 0, None)
        time.sleep(0.005)
        return 0

    def subscribe(self, topic: str, qos: int) -> tuple[int, int]:
        assert topic == "teslamate/fleet/cars/1/+"
        assert qos == 1
        return 0, 1

    def disconnect(self) -> None:
        return None


def test_session_reconnects_and_recovers_status(
    registered: tuple[TestClient, str], db_factory: sessionmaker[Session]
) -> None:
    _client, _csrf, data = _connector(registered)
    clients = iter((FakeClient(fail=True), FakeClient()))
    definition = ConnectorDefinition(
        id=data["id"], config_version=1, config=CONFIG, password=None
    )
    session = MqttConnectorSession(definition, db_factory, client_factory=lambda: next(clients))
    session.start()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        with db_factory() as db:
            connector = db.get(Connector, data["id"])
            if connector and connector.status == "connected":
                break
        time.sleep(0.02)
    session.stop()
    session.join(2)
    with db_factory() as db:
        connector = db.get(Connector, data["id"])
        assert connector
        assert connector.status == "connected"
        assert connector.last_connected_at is not None
        assert connector.last_error == ""
