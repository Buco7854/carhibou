from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field


class DashboardWidget(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1, max_length=120)
    type: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9-]*$")
    vehicle_id: str | None = Field(default=None, max_length=36)
    metric: str | None = Field(default=None, max_length=120)
    metrics: Annotated[list[str], Field(max_length=20)] | None = None
    title: str | None = Field(default=None, max_length=120)
    unit: str | None = Field(default=None, max_length=40)
    time_range_days: int | None = Field(default=None, ge=1, le=366)
    x: int = Field(ge=0, le=1000)
    y: int = Field(ge=0, le=100_000)
    w: int = Field(ge=1, le=12)
    h: int = Field(ge=1, le=100)
    settings: dict[str, Any] = Field(default_factory=dict)


class DashboardLayout(BaseModel):
    model_config = ConfigDict(extra="allow")

    widgets: Annotated[list[DashboardWidget], Field(max_length=100)] = Field(default_factory=list)


class DashboardWrite(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    is_default: bool = False
    layout: DashboardLayout = Field(default_factory=DashboardLayout)


class DashboardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    is_default: bool
    layout: DashboardLayout
    created_at: datetime
    updated_at: datetime
