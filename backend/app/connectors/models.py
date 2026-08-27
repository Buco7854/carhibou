from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.common.ids import new_id
from backend.app.common.models import Base, TimestampMixin
from backend.app.common.types import JSONType, JSONValue


class Connector(TimestampMixin, Base):
    __tablename__ = "connectors"

    # The connector and its shadow agent deliberately share an id. This keeps
    # ownership unambiguous without adding a second public identifier.
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    vehicle_id: Mapped[str] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(100))
    mapping_profile: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[JSONValue] = mapped_column(JSONType)
    encrypted_password: Mapped[str | None] = mapped_column(Text)
    config_version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="connecting")
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sample_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str] = mapped_column(Text, default="")

    vehicle = relationship("Vehicle", back_populates="connectors")
