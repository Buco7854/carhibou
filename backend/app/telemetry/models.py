from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.common.models import Base
from backend.app.common.time import utcnow
from backend.app.common.types import JSONType, JSONValue
from backend.app.telemetry.values import MetricValue


class Telemetry(Base):
    __tablename__ = "telemetry"
    __table_args__ = (
        Index("ix_telemetry_vehicle_recorded", "vehicle_id", "recorded_at"),
        Index("ix_telemetry_agent_recorded", "agent_id", "recorded_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"))
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    boot_id: Mapped[str] = mapped_column(String(36))
    sequence: Mapped[int] = mapped_column(Integer)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reporting_interval: Mapped[int | None] = mapped_column(Integer)
    event_driven: Mapped[bool] = mapped_column(Boolean, default=False)
    agent_data: Mapped[JSONValue] = mapped_column(JSONType, default=dict)

    observation_rows = relationship(
        "TelemetryObservation", cascade="all, delete-orphan", lazy="selectin"
    )
    position_observation = relationship(
        "TelemetryPositionObservation", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )

    @property
    def metrics(self) -> dict[str, object]:
        return {row.metric_key: row.value for row in self.observation_rows}

    def _position_value(self, key: str) -> float | None:
        if not self.position_observation:
            return None
        value = self.position_observation.value.get(key)
        return (
            float(value)
            if isinstance(value, (int, float)) and not isinstance(value, bool)
            else None
        )

    @property
    def latitude(self) -> float | None:
        return self._position_value("latitude")

    @property
    def longitude(self) -> float | None:
        return self._position_value("longitude")

    @property
    def altitude(self) -> float | None:
        return self._position_value("altitude")

    @property
    def gps_speed(self) -> float | None:
        return self._position_value("speed")

    @property
    def heading(self) -> float | None:
        return self._position_value("heading")

    @property
    def accuracy(self) -> float | None:
        return self._position_value("accuracy")


class TelemetryObservation(Base):
    __tablename__ = "telemetry_observations"
    __table_args__ = (
        UniqueConstraint("telemetry_id", "metric_key", "channel"),
        Index(
            "ix_telemetry_observations_vehicle_time",
            "vehicle_id",
            "observed_at",
        ),
        Index(
            "ix_telemetry_observations_vehicle_key_time",
            "vehicle_id",
            "metric_key",
            "observed_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telemetry_id: Mapped[str] = mapped_column(
        ForeignKey("telemetry.id", ondelete="CASCADE"), index=True
    )
    vehicle_id: Mapped[str] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    metric_key: Mapped[str] = mapped_column(String(120))
    value: Mapped[MetricValue] = mapped_column(JSONType, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    channel: Mapped[str] = mapped_column(String(16))
    method: Mapped[str] = mapped_column(String(16))


class TelemetryPositionObservation(Base):
    __tablename__ = "telemetry_position_observations"
    __table_args__ = (
        Index(
            "ix_telemetry_position_observations_vehicle_time",
            "vehicle_id",
            "observed_at",
        ),
    )

    telemetry_id: Mapped[str] = mapped_column(
        ForeignKey("telemetry.id", ondelete="CASCADE"), primary_key=True
    )
    vehicle_id: Mapped[str] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    value: Mapped[JSONValue] = mapped_column(JSONType)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    channel: Mapped[str] = mapped_column(String(16))
    method: Mapped[str] = mapped_column(String(16))


class MetricCandidate(Base):
    __tablename__ = "telemetry_metric_candidates"
    __table_args__ = (Index("ix_metric_candidates_vehicle_key", "vehicle_id", "metric_key"),)

    vehicle_id: Mapped[str] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), primary_key=True
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True
    )
    channel: Mapped[str] = mapped_column(String(16), primary_key=True)
    metric_key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[MetricValue] = mapped_column(JSONType, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    method: Mapped[str] = mapped_column(String(16))
    reporting_interval: Mapped[int | None] = mapped_column(Integer)
    event_driven: Mapped[bool] = mapped_column(Boolean, default=False)
    telemetry_id: Mapped[str] = mapped_column(
        ForeignKey("telemetry.id", ondelete="CASCADE"), index=True
    )


class PositionCandidate(Base):
    __tablename__ = "telemetry_position_candidates"

    vehicle_id: Mapped[str] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), primary_key=True
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True
    )
    channel: Mapped[str] = mapped_column(String(16), primary_key=True)
    value: Mapped[JSONValue] = mapped_column(JSONType)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    method: Mapped[str] = mapped_column(String(16))
    reporting_interval: Mapped[int | None] = mapped_column(Integer)
    event_driven: Mapped[bool] = mapped_column(Boolean, default=False)
    telemetry_id: Mapped[str] = mapped_column(
        ForeignKey("telemetry.id", ondelete="CASCADE"), index=True
    )


class SourceContactPeriod(Base):
    __tablename__ = "telemetry_source_contact_periods"
    __table_args__ = (Index("ix_source_contact_periods_source_started", "source_id", "started_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_contact_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    liveness_window_seconds: Mapped[int] = mapped_column(Integer)
