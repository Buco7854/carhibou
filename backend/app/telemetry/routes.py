from fastapi import APIRouter

from backend.app.auth.dependencies import CurrentDevice, Db
from backend.app.telemetry.schemas import BatchResponse, TelemetryBatch
from backend.app.telemetry.services import ingest_batch

router = APIRouter(prefix="/device/telemetry", tags=["telemetry ingestion"])


@router.post("/batch", response_model=BatchResponse)
def telemetry_batch(data: TelemetryBatch, db: Db, device: CurrentDevice) -> BatchResponse:
    result = ingest_batch(db, device, data)
    db.commit()
    return BatchResponse(
        accepted=result.accepted,
        duplicates=result.duplicates,
        config_version=device.config_version,
    )
