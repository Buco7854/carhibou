from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.common.time import as_utc, utcnow
from backend.app.devices.models import Device
from backend.app.hooks.models import Hook, HookExecution, Trigger
from backend.app.jobs.models import Job
from backend.app.telemetry.models import Telemetry
from backend.app.telemetry.schemas import TelemetryBatch, TelemetrySample
from backend.app.vehicle_state.models import VehicleState
from backend.app.vehicles.models import Vehicle


@dataclass
class IngestionResult:
    accepted: list[str]
    duplicates: list[str]


def _telemetry_model(device: Device, boot_id: str, sample: TelemetrySample) -> Telemetry:
    position = sample.position
    return Telemetry(
        id=str(sample.id),
        vehicle_id=device.vehicle_id,
        device_id=device.id,
        boot_id=boot_id,
        sequence=sample.sequence,
        recorded_at=as_utc(sample.recorded_at),
        latitude=position.latitude if position else None,
        longitude=position.longitude if position else None,
        altitude=position.altitude if position else None,
        gps_speed=position.speed if position else None,
        heading=position.heading if position else None,
        accuracy=position.accuracy if position else None,
        metrics=dict(sample.metrics),
        device_data=dict(sample.device),
    )


def _update_current_state(db: Session, telemetry: Telemetry) -> None:
    state = db.get(VehicleState, telemetry.vehicle_id)
    if state and as_utc(state.updated_at) > as_utc(telemetry.recorded_at):
        return
    previous_metrics = state.latest_metrics if state else {}
    previous_device = state.device_state if state else {}
    values = {
        "telemetry_id": telemetry.id,
        "updated_at": telemetry.recorded_at,
        "latitude": telemetry.latitude,
        "longitude": telemetry.longitude,
        "altitude": telemetry.altitude,
        "gps_speed": telemetry.gps_speed,
        "heading": telemetry.heading,
        "accuracy": telemetry.accuracy,
        "latest_metrics": {**previous_metrics, **telemetry.metrics},
        "device_state": {**previous_device, **telemetry.device_data},
    }
    if state:
        for key, value in values.items():
            setattr(state, key, value)
    else:
        db.add(VehicleState(vehicle_id=telemetry.vehicle_id, **values))


def _enqueue_hooks(db: Session, telemetry: Telemetry) -> None:
    trigger = Trigger(
        type="telemetry.received",
        version=1,
        occurred_at=telemetry.recorded_at,
        vehicle_id=telemetry.vehicle_id,
        device_id=telemetry.device_id,
        telemetry_id=telemetry.id,
        payload={"telemetry_id": telemetry.id},
    )
    db.add(trigger)
    db.flush()
    owner_id = db.scalar(select(Vehicle.owner_id).where(Vehicle.id == telemetry.vehicle_id))
    hooks = db.scalars(
        select(Hook).where(
            Hook.owner_id == owner_id,
            Hook.enabled.is_(True),
            Hook.trigger_type == trigger.type,
            (Hook.vehicle_id.is_(None) | (Hook.vehicle_id == telemetry.vehicle_id)),
        )
    )
    for hook in hooks:
        execution = HookExecution(
            hook_id=hook.id,
            trigger_id=trigger.id,
            telemetry_id=telemetry.id,
            status="pending",
        )
        db.add(execution)
        db.flush()
        db.add(Job(type="hook.execute", payload={"execution_id": execution.id}))


def ingest_batch(db: Session, device: Device, batch: TelemetryBatch) -> IngestionResult:
    # Serialize ingestion per vehicle. This prevents two devices/requests from racing
    # the initial current-state row or rewinding merged JSON state.
    db.execute(select(Vehicle.id).where(Vehicle.id == device.vehicle_id).with_for_update())
    result = IngestionResult(accepted=[], duplicates=[])
    for sample in batch.samples:
        telemetry = _telemetry_model(device, str(batch.boot_id), sample)
        try:
            with db.begin_nested():
                db.add(telemetry)
                db.flush()
        except IntegrityError:
            result.duplicates.append(telemetry.id)
            continue
        _update_current_state(db, telemetry)
        _enqueue_hooks(db, telemetry)
        result.accepted.append(telemetry.id)
    device.last_seen_at = utcnow()
    return result
