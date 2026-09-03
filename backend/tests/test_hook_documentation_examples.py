import copy
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.app.agents.models import Agent
from backend.app.common import model_registry  # noqa: F401
from backend.app.common.models import Base
from backend.app.common.settings import get_settings
from backend.app.hooks.models import Hook, HookExecution, HookState, Trigger
from backend.app.hooks.runtime import RuntimeResult, build_runtime_input, run_hook_process
from backend.app.telemetry.models import SourceContactPeriod
from backend.app.telemetry.resolution import resolve_vehicle
from backend.app.telemetry.schemas import TelemetryBatch
from backend.app.telemetry.services import ingest_batch
from backend.app.vehicles.models import Vehicle

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HOOK_GUIDE = PROJECT_ROOT / "docs/user-guide/hooks.md"
PYTHON_FENCE = re.compile(r"```python\n(?P<source>.*?)\n```", re.DOTALL)
EXAMPLE_MARKER = re.compile(r"^# hook-example: (?P<name>[a-z0-9-]+)$", re.MULTILINE)

EXPECTED_DOCUMENTED_EXAMPLES = {
    "current-state-of-charge",
    "historical-context",
    "low-state-of-charge",
    "charging-finished",
    "gate-on-arrival",
    "forward-positions-to-traccar",
}

# Copied from frontend/src/views/HooksView.vue defaultSource at commit 061f14a.
# The frontend owns that file; this fixture executes the starter users receive
# without making the backend test depend on or write into the frontend tree.
FRONTEND_DEFAULT_SOURCE = """# Runs after telemetry is safely stored.
soc = ctx.telemetry.current.readings.get("battery.soc")
if soc is None or not soc.fresh:
    return

armed = ctx.state.get("armed", True)
if armed and soc.value < 20:
    ctx.log.warning("Battery is low", soc=soc.value, observed_at=soc.observed_at)
    ctx.state["armed"] = False
elif not armed and soc.value > 23:
    ctx.state["armed"] = True
"""


def _documented_examples() -> dict[str, str]:
    examples: dict[str, str] = {}
    for match in PYTHON_FENCE.finditer(HOOK_GUIDE.read_text(encoding="utf-8")):
        source = match.group("source")
        marker = EXAMPLE_MARKER.search(source)
        assert marker is not None, f"unmarked Python fence begins with {source.splitlines()[0]!r}"
        name = marker.group("name")
        assert name not in examples, f"duplicate hook example marker: {name}"
        examples[name] = source
    return examples


def _sample(
    *,
    sequence: int,
    observed_at: datetime,
    observations: list[dict[str, object]],
    latitude: float,
    longitude: float,
    speed: float,
) -> dict[str, object]:
    return {
        "id": str(uuid4()),
        "sequence": sequence,
        "recorded_at": observed_at.isoformat(),
        "position": {
            "value": {
                "latitude": latitude,
                "longitude": longitude,
                "speed": speed,
                "heading": 90,
            },
            "observed_at": observed_at.isoformat(),
            "channel": "gnss",
            "method": "direct",
        },
        "observations": [
            {
                **observation,
                "observed_at": observed_at.isoformat(),
                "channel": "can",
                "method": "direct",
            }
            for observation in observations
        ],
        "agent": {"queue_depth": 0},
        "reporting_interval": 30,
    }


def _seed_v2_fixture(database_url: str) -> tuple[Engine, str, str, str]:
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    now = datetime.now(UTC).replace(microsecond=0)
    old_at = now - timedelta(minutes=90)
    current_at = now - timedelta(seconds=10)
    with Session(engine) as db:
        vehicle = Vehicle(name="Documentation car", manufacturer="Citroën", model="C-Zero")
        db.add(vehicle)
        db.flush()
        agent = Agent(
            vehicle_id=vehicle.id,
            name="Documentation agent",
            credential_hash="d" * 64,
            implementation_id="custom",
            protocol_version=2,
            agent_version="test",
            hostname="docs-fixture",
        )
        db.add(agent)
        db.flush()
        batch = TelemetryBatch.model_validate(
            {
                "boot_id": str(uuid4()),
                "samples": [
                    _sample(
                        sequence=1,
                        observed_at=old_at,
                        observations=[
                            {"key": "battery.soc", "value": 80},
                            {"key": "charging.active", "value": True},
                            {"key": "tyre.front_left_pressure", "value": 2.3},
                        ],
                        latitude=48.8,
                        longitude=2.3,
                        speed=18.52,
                    ),
                    _sample(
                        sequence=2,
                        observed_at=current_at,
                        observations=[
                            {"key": "battery.soc", "value": 18},
                            {"key": "charging.active", "value": False},
                        ],
                        latitude=48.8566,
                        longitude=2.3522,
                        speed=37.04,
                    ),
                ],
            }
        )
        result = ingest_batch(db, agent, batch)
        db.commit()

        readings, position = resolve_vehicle(db, vehicle.id)
        assert readings["battery.soc"]["fresh"] is True
        assert readings["tyre.front_left_pressure"]["fresh"] is False
        assert position is not None and position["fresh"] is True
        assert db.scalar(
            select(SourceContactPeriod).where(SourceContactPeriod.source_id == agent.id)
        )
        trigger = db.scalar(
            select(Trigger)
            .where(Trigger.telemetry_id == result.accepted[-1])
            .order_by(Trigger.created_at.desc())
        )
        assert trigger is not None
        return engine, vehicle.id, trigger.id, result.accepted[-1]


def _runtime_data(
    engine: Engine,
    *,
    vehicle_id: str,
    trigger_id: str,
    telemetry_id: str,
    source: str,
    state: dict[str, object] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    with Session(engine) as db:
        hook = Hook(
            vehicle_id=vehicle_id,
            name=f"Documentation example {uuid4()}",
            description="",
            enabled=False,
            trigger_type="telemetry.received",
            source=source,
            timeout_seconds=10,
        )
        db.add(hook)
        db.flush()
        if state is not None:
            db.add(HookState(hook_id=hook.id, value=state))
        execution = HookExecution(
            hook_id=hook.id,
            trigger_id=trigger_id,
            telemetry_id=telemetry_id,
            dry_run=True,
            status="pending",
        )
        db.add(execution)
        db.commit()
        _hook, data, secrets = build_runtime_input(db, execution)
        return data, secrets


def _run(data: dict[str, Any], secrets: list[str], name: str) -> RuntimeResult:
    result = run_hook_process(data, timeout=10, secrets=secrets)
    assert result.status == "success", f"{name}: {result.error}"
    return result


def _messages(result: RuntimeResult) -> list[str]:
    return [str(record.get("message", "")) for record in result.logs]


def test_all_shipped_hook_examples_execute_in_the_real_child_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    examples = _documented_examples()
    assert set(examples) == EXPECTED_DOCUMENTED_EXAMPLES
    combined = "\n".join(examples.values())
    for capability in (
        "ctx.telemetry.triggering",
        "ctx.telemetry.current",
        "ctx.telemetry.state_at(",
        "ctx.telemetry.history(",
    ):
        assert capability in combined, f"the guide has no example for {capability}"

    database_url = f"sqlite:///{tmp_path / 'hook-examples.sqlite3'}"
    monkeypatch.setenv("CARHIBOU_DATABASE_URL", database_url)
    get_settings.cache_clear()
    request.addfinalizer(get_settings.cache_clear)
    engine, vehicle_id, trigger_id, telemetry_id = _seed_v2_fixture(database_url)
    request.addfinalizer(engine.dispose)

    initial_states: dict[str, dict[str, object]] = {
        "gate-on-arrival": {"inside_home": False},
    }
    results: dict[str, RuntimeResult] = {}
    inputs: dict[str, tuple[dict[str, Any], list[str]]] = {}
    for name, source in examples.items():
        data, secrets = _runtime_data(
            engine,
            vehicle_id=vehicle_id,
            trigger_id=trigger_id,
            telemetry_id=telemetry_id,
            source=source,
            state=initial_states.get(name),
        )
        inputs[name] = (data, secrets)
        results[name] = _run(data, secrets, name)

    assert "Current state of charge" in _messages(results["current-state-of-charge"])
    assert "Inspected recent telemetry" in _messages(results["historical-context"])
    assert results["low-state-of-charge"].state["armed"] is False
    assert "Battery SOC is low" in _messages(results["low-state-of-charge"])
    assert results["charging-finished"].state["charging"] is False
    assert "Would send charging notification" in _messages(results["charging-finished"])
    assert results["gate-on-arrival"].state["inside_home"] is True
    assert "Would open gate" in _messages(results["gate-on-arrival"])
    traccar_logs = [
        record
        for record in results["forward-positions-to-traccar"].logs
        if record.get("message") == "Would forward position to Traccar"
    ]
    assert len(traccar_logs) == 2
    traccar_fields = [record.get("fields") for record in traccar_logs]
    assert all(isinstance(fields, dict) for fields in traccar_fields)
    assert [fields["batt"] for fields in traccar_fields if isinstance(fields, dict)] == [80, 18]
    speeds = [fields["speed"] for fields in traccar_fields if isinstance(fields, dict)]
    assert speeds == pytest.approx([10, 20])

    default_data, default_secrets = _runtime_data(
        engine,
        vehicle_id=vehicle_id,
        trigger_id=trigger_id,
        telemetry_id=telemetry_id,
        source=FRONTEND_DEFAULT_SOURCE,
    )
    default_result = _run(default_data, default_secrets, "frontend-default-source")
    assert default_result.state["armed"] is False
    assert "Battery is low" in _messages(default_result)

    current_data, current_secrets = inputs["current-state-of-charge"]
    missing = copy.deepcopy(current_data)
    missing["telemetry_context"]["current"]["readings"].pop("battery.soc")
    missing_result = _run(missing, current_secrets, "current-state-of-charge/missing")
    assert missing_result.logs == [] and missing_result.state == {}
    stale = copy.deepcopy(current_data)
    stale["telemetry_context"]["current"]["readings"]["battery.soc"]["fresh"] = False
    stale_result = _run(stale, current_secrets, "current-state-of-charge/stale")
    assert stale_result.logs == [] and stale_result.state == {}

    gate_data, gate_secrets = inputs["gate-on-arrival"]
    without_position = copy.deepcopy(gate_data)
    without_position["telemetry_context"]["triggering"] = [
        row
        for row in without_position["telemetry_context"]["triggering"]
        if row["key"] != "position"
    ]
    gate_result = _run(without_position, gate_secrets, "gate-on-arrival/no-position")
    assert gate_result.logs == [] and gate_result.state == {"inside_home": False}

    stale_arrival = copy.deepcopy(gate_data)
    stale_positions = [
        row for row in stale_arrival["telemetry_context"]["triggering"] if row["key"] == "position"
    ]
    assert len(stale_positions) == 2
    stale_positions[0]["value"] = {"latitude": 48.8566, "longitude": 2.3522}
    stale_arrival["telemetry_context"]["triggering"] = [stale_positions[0]]
    stale_gate_result = _run(stale_arrival, gate_secrets, "gate-on-arrival/stale")
    assert stale_gate_result.logs == []
    assert stale_gate_result.state == {"inside_home": False}

    traccar_data, traccar_secrets = inputs["forward-positions-to-traccar"]
    without_positions = copy.deepcopy(traccar_data)
    without_positions["telemetry_context"]["triggering"] = [
        row
        for row in without_positions["telemetry_context"]["triggering"]
        if row["key"] != "position"
    ]
    assert without_positions["telemetry_context"]["triggering"]
    traccar_result = _run(
        without_positions,
        traccar_secrets,
        "forward-positions-to-traccar/no-position",
    )
    assert _messages(traccar_result) == ["No positions to forward in this run"]
