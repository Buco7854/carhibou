from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HookWrite(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=5000)
    enabled: bool = False
    trigger_type: Literal["telemetry.received"] = "telemetry.received"
    vehicle_id: str | None = None
    source: str = Field(min_length=1, max_length=100000)
    timeout_seconds: int = Field(default=10, ge=1, le=120)


class HookExecutionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    created_at: datetime


class HookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    enabled: bool
    trigger_type: str
    vehicle_id: str | None
    source: str
    timeout_seconds: int
    revision: int
    created_at: datetime
    updated_at: datetime
    # Null until a hook has run. A hook that has never run and one whose last run
    # failed are different things, and the list has to show the difference
    # without asking after each hook separately.
    last_execution: HookExecutionSummary | None = None


class HookRevisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    revision: int
    source: str
    created_by: str
    created_at: datetime


class HookTestRequest(BaseModel):
    telemetry_id: str
    dry_run: bool = True


class HookExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    hook_id: str
    trigger_id: str
    telemetry_id: str | None
    dry_run: bool
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    duration_seconds: float | None
    logs: list[dict[str, object]]
    log_count: int
    logs_truncated: bool
    error: str | None
    created_at: datetime


class HookExecutionLogPage(BaseModel):
    total: int
    limit: int
    offset: int
    logs: list[dict[str, object]]
