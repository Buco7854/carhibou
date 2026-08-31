from fastapi import APIRouter

from backend.app.auth.dependencies import CurrentAgent, CurrentUser, Db
from backend.app.telemetry.registry import CANONICAL_METRICS
from backend.app.telemetry.schemas import (
    BatchResponse,
    MetricDefinitionResponse,
    MetricRegistryResponse,
    TelemetryBatch,
)
from backend.app.telemetry.services import ingest_batch

router = APIRouter(prefix="/agent/telemetry", tags=["telemetry ingestion"])
metrics_router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.post("/batch", response_model=BatchResponse)
def telemetry_batch(data: TelemetryBatch, db: Db, agent: CurrentAgent) -> BatchResponse:
    result = ingest_batch(db, agent, data)
    db.commit()
    return BatchResponse(
        accepted=result.accepted,
        duplicates=result.duplicates,
        config_version=agent.config_version,
    )


@metrics_router.get("/registry", response_model=MetricRegistryResponse)
def metric_registry(auth: CurrentUser) -> MetricRegistryResponse:
    """The canonical metrics a profile or hook can rely on meaning the same thing.

    Published because the alternative is authors reading the registry source, or
    guessing a key and having it land in the namespaced extension space where
    nothing understands it.
    """

    del auth
    return MetricRegistryResponse(
        metrics=[
            MetricDefinitionResponse(
                key=definition.key,
                unit=definition.unit,
                meaning=definition.meaning,
                kind=definition.kind,
                value_type=definition.value_type,
                retained=definition.retain_stale,
                freshness_seconds=int(definition.freshness.total_seconds()),
            )
            for definition in sorted(CANONICAL_METRICS.values(), key=lambda item: item.key)
        ]
    )
