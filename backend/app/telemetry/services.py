from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.agents.models import Agent
from backend.app.common.time import as_utc, utcnow
from backend.app.hooks.models import Hook, HookExecution, Trigger
from backend.app.jobs.models import Job
from backend.app.telemetry.contacts import latest_contact_period
from backend.app.telemetry.models import (
    MetricCandidate,
    PositionCandidate,
    SourceContactPeriod,
    Telemetry,
    TelemetryObservation,
    TelemetryPositionObservation,
)
from backend.app.telemetry.registry import normalize_value
from backend.app.telemetry.resolution import resolve_vehicle
from backend.app.telemetry.schemas import Observation, TelemetryBatch, TelemetrySample
from backend.app.vehicle_state.models import VehicleState
from backend.app.vehicles.models import Vehicle


@dataclass
class IngestionResult:
    accepted: list[str]
    duplicates: list[str]


def touch_source_contact(
    db: Session,
    source_id: str,
    contacted_at: datetime,
    liveness_window_seconds: int,
) -> None:
    contacted_at = as_utc(contacted_at)
    latest_period = latest_contact_period(db, source_id)
    if latest_period and as_utc(latest_period.last_contact_at) > contacted_at:
        return
    if latest_period is None or contacted_at > as_utc(latest_period.last_contact_at) + timedelta(
        seconds=latest_period.liveness_window_seconds
    ):
        db.add(
            SourceContactPeriod(
                source_id=source_id,
                started_at=contacted_at,
                last_contact_at=contacted_at,
                liveness_window_seconds=liveness_window_seconds,
            )
        )
    else:
        latest_period.last_contact_at = contacted_at
        latest_period.liveness_window_seconds = liveness_window_seconds


def _accepted_observations(sample: TelemetrySample) -> list[Observation]:
    accepted: list[Observation] = []
    for observation in sample.observations:
        valid, value = normalize_value(observation.key, observation.value)
        if not valid:
            continue
        accepted.append(observation.model_copy(update={"value": value}))
    return accepted


def _telemetry_model(
    agent: Agent,
    boot_id: str,
    sample: TelemetrySample,
) -> Telemetry:
    return Telemetry(
        id=str(sample.id),
        vehicle_id=agent.vehicle_id,
        agent_id=agent.id,
        boot_id=boot_id,
        sequence=sample.sequence,
        recorded_at=as_utc(sample.recorded_at),
        reporting_interval=sample.reporting_interval,
        event_driven=sample.event_driven,
        agent_data=dict(sample.agent),
    )


def _apply_metric_candidate(
    db: Session,
    telemetry: Telemetry,
    observation: Observation,
) -> None:
    identity = (
        telemetry.vehicle_id,
        telemetry.agent_id,
        observation.channel,
        observation.key,
    )
    row = db.get(MetricCandidate, identity)
    observed_at = as_utc(observation.observed_at)
    if row and as_utc(row.observed_at) >= observed_at:
        return
    values = {
        "value": observation.value,
        "observed_at": observed_at,
        "method": observation.method,
        "reporting_interval": telemetry.reporting_interval,
        "event_driven": telemetry.event_driven,
        "telemetry_id": telemetry.id,
    }
    if row:
        for key, value in values.items():
            setattr(row, key, value)
    else:
        db.add(
            MetricCandidate(
                vehicle_id=telemetry.vehicle_id,
                source_id=telemetry.agent_id,
                channel=observation.channel,
                metric_key=observation.key,
                **values,
            )
        )


def _apply_position_candidate(db: Session, telemetry: Telemetry, sample: TelemetrySample) -> None:
    position = sample.position
    if position is None:
        return
    identity = (telemetry.vehicle_id, telemetry.agent_id, position.channel)
    row = db.get(PositionCandidate, identity)
    observed_at = as_utc(position.observed_at)
    if not row or as_utc(row.observed_at) < observed_at:
        values = {
            "value": position.value.model_dump(mode="json"),
            "observed_at": observed_at,
            "method": position.method,
            "reporting_interval": telemetry.reporting_interval,
            "event_driven": telemetry.event_driven,
            "telemetry_id": telemetry.id,
        }
        if row:
            for key, value in values.items():
                setattr(row, key, value)
        else:
            db.add(
                PositionCandidate(
                    vehicle_id=telemetry.vehicle_id,
                    source_id=telemetry.agent_id,
                    channel=position.channel,
                    **values,
                )
            )
    speed = Observation(
        key="vehicle.speed",
        value=position.value.speed,
        observed_at=position.observed_at,
        channel="gnss",
        method=position.method,
    )
    _apply_metric_candidate(db, telemetry, speed)


def _update_current_state(db: Session, vehicle_id: str, accepted: list[Telemetry]) -> None:
    if not accepted:
        return
    state = db.get(VehicleState, vehicle_id)
    newest = max(accepted, key=lambda row: (as_utc(row.recorded_at), row.sequence, row.id))
    previous_updated = as_utc(state.updated_at) if state else None
    updated_at = max(
        [as_utc(row.recorded_at) for row in accepted]
        + ([previous_updated] if previous_updated else [])
    )
    agent_state = dict(state.agent_state) if state else {}
    if previous_updated is None or as_utc(newest.recorded_at) >= previous_updated:
        agent_state.update(newest.agent_data)
    readings, position = resolve_vehicle(db, vehicle_id)
    telemetry_id = newest.id
    if state and updated_at != as_utc(newest.recorded_at):
        telemetry_id = state.telemetry_id
    values = {
        "telemetry_id": telemetry_id,
        "updated_at": updated_at,
        "readings": readings,
        "position": position,
        "agent_state": agent_state,
    }
    if state:
        for key, value in values.items():
            setattr(state, key, value)
    else:
        db.add(VehicleState(vehicle_id=vehicle_id, **values))


def _enqueue_hooks(db: Session, samples: list[Telemetry]) -> None:
    if not samples:
        return
    latest = samples[-1]
    trigger = Trigger(
        type="telemetry.received",
        version=2,
        occurred_at=latest.recorded_at,
        vehicle_id=latest.vehicle_id,
        agent_id=latest.agent_id,
        telemetry_id=latest.id,
        payload={
            "telemetry_id": latest.id,
            "telemetry_ids": [row.id for row in samples],
            "boot_id": latest.boot_id,
        },
    )
    db.add(trigger)
    db.flush()
    hooks = db.scalars(
        select(Hook).where(
            Hook.enabled.is_(True),
            Hook.trigger_type == trigger.type,
            (Hook.vehicle_id.is_(None) | (Hook.vehicle_id == latest.vehicle_id)),
        )
    )
    for hook in hooks:
        execution = HookExecution(
            hook_id=hook.id,
            trigger_id=trigger.id,
            telemetry_id=latest.id,
            status="pending",
        )
        db.add(execution)
        db.flush()
        db.add(Job(type="hook.execute", payload={"execution_id": execution.id}))


def ingest_batch(db: Session, agent: Agent, batch: TelemetryBatch) -> IngestionResult:
    db.execute(select(Vehicle.id).where(Vehicle.id == agent.vehicle_id).with_for_update())
    result = IngestionResult(accepted=[], duplicates=[])
    stored: list[Telemetry] = []
    incoming_ids = [str(sample.id) for sample in batch.samples]
    existing_ids = set(db.scalars(select(Telemetry.id).where(Telemetry.id.in_(incoming_ids))))
    for sample in batch.samples:
        observations = _accepted_observations(sample)
        telemetry = _telemetry_model(agent, str(batch.boot_id), sample)
        if telemetry.id in existing_ids:
            result.duplicates.append(telemetry.id)
            continue
        db.add(telemetry)
        db.flush([telemetry])
        for observation in observations:
            db.add(
                TelemetryObservation(
                    telemetry_id=telemetry.id,
                    vehicle_id=telemetry.vehicle_id,
                    source_id=telemetry.agent_id,
                    metric_key=observation.key,
                    value=observation.value,
                    observed_at=as_utc(observation.observed_at),
                    channel=observation.channel,
                    method=observation.method,
                )
            )
            _apply_metric_candidate(db, telemetry, observation)
        if sample.position:
            db.add(
                TelemetryPositionObservation(
                    telemetry_id=telemetry.id,
                    vehicle_id=telemetry.vehicle_id,
                    source_id=telemetry.agent_id,
                    value=sample.position.value.model_dump(mode="json"),
                    observed_at=as_utc(sample.position.observed_at),
                    channel=sample.position.channel,
                    method=sample.position.method,
                )
            )
        _apply_position_candidate(db, telemetry, sample)
        stored.append(telemetry)
        result.accepted.append(telemetry.id)
    db.flush()
    stored.sort(key=lambda row: (as_utc(row.recorded_at), row.sequence, row.id))
    _update_current_state(db, agent.vehicle_id, stored)
    _enqueue_hooks(db, stored)
    agent.last_seen_at = utcnow()
    liveness = max([sample.reporting_interval or 0 for sample in batch.samples] + [15])
    touch_source_contact(db, agent.id, agent.last_seen_at, liveness)
    return result
