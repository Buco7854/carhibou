from fastapi import APIRouter

from backend.app.auth.dependencies import CurrentAgent, Db
from backend.app.telemetry.schemas import BatchResponse, TelemetryBatch
from backend.app.telemetry.services import ingest_batch

router = APIRouter(prefix="/agent/telemetry", tags=["telemetry ingestion"])


@router.post("/batch", response_model=BatchResponse)
def telemetry_batch(data: TelemetryBatch, db: Db, agent: CurrentAgent) -> BatchResponse:
    result = ingest_batch(db, agent, data)
    db.commit()
    return BatchResponse(
        accepted=result.accepted,
        duplicates=result.duplicates,
        config_version=agent.config_version,
    )
