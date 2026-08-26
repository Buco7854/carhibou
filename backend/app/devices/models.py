from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.common.ids import new_id
from backend.app.common.models import Base, TimestampMixin
from backend.app.common.types import JSONType, JSONValue


class Device(TimestampMixin, Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    vehicle_id: Mapped[str] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    credential_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    credential_version: Mapped[int] = mapped_column(Integer, default=1)
    agent_version: Mapped[str | None] = mapped_column(String(50))
    hostname: Mapped[str | None] = mapped_column(String(255))
    hardware: Mapped[JSONValue] = mapped_column(JSONType, default=dict)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_config_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    config_version: Mapped[int] = mapped_column(Integer, default=1)
    # How often the agent takes a sample, and how often it drains its queue.
    # Both are per device because agents on one account are not alike: a car on
    # a metered connection wants a slower upload than a daily driver.
    #
    # The parked pair applies while the agent judges the vehicle out of use.
    # Its server_default matches the driving pair so that migrating an existing
    # deployment changes nothing until somebody chooses a slower parked cadence;
    # a device created from now on gets the interface's "Standard" preset.
    sampling_seconds: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    upload_seconds: Mapped[int] = mapped_column(Integer, default=5, server_default="30")
    parked_sampling_seconds: Mapped[int] = mapped_column(Integer, default=300, server_default="5")
    parked_upload_seconds: Mapped[int] = mapped_column(Integer, default=300, server_default="30")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    vehicle = relationship("Vehicle", back_populates="devices")


class EnrollmentToken(Base):
    __tablename__ = "device_enrollment_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    vehicle_id: Mapped[str] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    intended_name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Carried from the enrollment form to the device the token creates, so a
    # agent starts on the cadence it was enrolled with rather than a default it
    # then has to be corrected away from.
    sampling_seconds: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    upload_seconds: Mapped[int] = mapped_column(Integer, default=5, server_default="30")
    parked_sampling_seconds: Mapped[int] = mapped_column(Integer, default=300, server_default="5")
    parked_upload_seconds: Mapped[int] = mapped_column(Integer, default=300, server_default="30")
