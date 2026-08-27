from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.agents.constants import STANDARD_CADENCE
from backend.app.common.ids import new_id
from backend.app.common.models import Base, TimestampMixin
from backend.app.common.types import JSONType, JSONValue


class Agent(TimestampMixin, Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    vehicle_id: Mapped[str] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    credential_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    credential_version: Mapped[int] = mapped_column(Integer, default=1)
    implementation_id: Mapped[str] = mapped_column(String(100))
    protocol_version: Mapped[int] = mapped_column(Integer)
    agent_version: Mapped[str] = mapped_column(String(50))
    hostname: Mapped[str | None] = mapped_column(String(255))
    hardware: Mapped[JSONValue] = mapped_column(JSONType, default=dict)
    vehicle_profile: Mapped[str | None] = mapped_column(String(120))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_config_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    config_version: Mapped[int] = mapped_column(Integer, default=1)
    # ORM and database defaults intentionally share the interface's Standard preset.
    sampling_seconds: Mapped[int] = mapped_column(
        Integer,
        default=STANDARD_CADENCE.sampling_seconds,
        server_default=str(STANDARD_CADENCE.sampling_seconds),
    )
    upload_seconds: Mapped[int] = mapped_column(
        Integer,
        default=STANDARD_CADENCE.upload_seconds,
        server_default=str(STANDARD_CADENCE.upload_seconds),
    )
    parked_sampling_seconds: Mapped[int] = mapped_column(
        Integer,
        default=STANDARD_CADENCE.parked_sampling_seconds,
        server_default=str(STANDARD_CADENCE.parked_sampling_seconds),
    )
    parked_upload_seconds: Mapped[int] = mapped_column(
        Integer,
        default=STANDARD_CADENCE.parked_upload_seconds,
        server_default=str(STANDARD_CADENCE.parked_upload_seconds),
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    vehicle = relationship("Vehicle", back_populates="agents")


class AgentEnrollmentToken(Base):
    __tablename__ = "agent_enrollment_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    vehicle_id: Mapped[str] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    intended_name: Mapped[str] = mapped_column(String(120))
    implementation_id: Mapped[str] = mapped_column(String(100))
    vehicle_profile: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Carried from the enrollment form to the agent the token creates, so an
    # agent starts on the cadence it was enrolled with rather than a default it
    # then has to be corrected away from.
    sampling_seconds: Mapped[int] = mapped_column(
        Integer,
        default=STANDARD_CADENCE.sampling_seconds,
        server_default=str(STANDARD_CADENCE.sampling_seconds),
    )
    upload_seconds: Mapped[int] = mapped_column(
        Integer,
        default=STANDARD_CADENCE.upload_seconds,
        server_default=str(STANDARD_CADENCE.upload_seconds),
    )
    parked_sampling_seconds: Mapped[int] = mapped_column(
        Integer,
        default=STANDARD_CADENCE.parked_sampling_seconds,
        server_default=str(STANDARD_CADENCE.parked_sampling_seconds),
    )
    parked_upload_seconds: Mapped[int] = mapped_column(
        Integer,
        default=STANDARD_CADENCE.parked_upload_seconds,
        server_default=str(STANDARD_CADENCE.parked_upload_seconds),
    )
