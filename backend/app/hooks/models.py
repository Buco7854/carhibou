from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.common.ids import new_id
from backend.app.common.models import Base, TimestampMixin
from backend.app.common.time import utcnow
from backend.app.common.types import JSONType, JSONValue


class Trigger(Base):
    __tablename__ = "triggers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    type: Mapped[str] = mapped_column(String(80), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    vehicle_id: Mapped[str | None] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    device_id: Mapped[str | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"))
    telemetry_id: Mapped[str | None] = mapped_column(
        ForeignKey("telemetry.id", ondelete="CASCADE"), index=True
    )
    payload: Mapped[JSONValue] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Hook(TimestampMixin, Base):
    __tablename__ = "hooks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    vehicle_id: Mapped[str | None] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    trigger_type: Mapped[str] = mapped_column(String(80), default="telemetry.received")
    source: Mapped[str] = mapped_column(Text)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=10)
    revision: Mapped[int] = mapped_column(Integer, default=1)


class HookRevision(Base):
    __tablename__ = "hook_revisions"
    __table_args__ = (UniqueConstraint("hook_id", "revision"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    hook_id: Mapped[str] = mapped_column(ForeignKey("hooks.id", ondelete="CASCADE"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HookState(Base):
    __tablename__ = "hook_state"

    hook_id: Mapped[str] = mapped_column(
        ForeignKey("hooks.id", ondelete="CASCADE"), primary_key=True
    )
    value: Mapped[JSONValue] = mapped_column(JSONType, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HookExecution(Base):
    __tablename__ = "hook_executions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    hook_id: Mapped[str] = mapped_column(ForeignKey("hooks.id", ondelete="CASCADE"), index=True)
    trigger_id: Mapped[str] = mapped_column(
        ForeignKey("triggers.id", ondelete="CASCADE"), index=True
    )
    telemetry_id: Mapped[str | None] = mapped_column(
        ForeignKey("telemetry.id", ondelete="SET NULL"), index=True
    )
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    logs: Mapped[list[JSONValue]] = mapped_column(JSONType, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
