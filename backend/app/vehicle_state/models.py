from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.common.models import Base
from backend.app.common.types import JSONType, JSONValue


class VehicleState(Base):
    __tablename__ = "vehicle_state"

    vehicle_id: Mapped[str] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), primary_key=True
    )
    telemetry_id: Mapped[str] = mapped_column(ForeignKey("telemetry.id", ondelete="CASCADE"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    readings: Mapped[JSONValue] = mapped_column(JSONType, default=dict)
    position: Mapped[JSONValue | None] = mapped_column(JSONType)
    agent_state: Mapped[JSONValue] = mapped_column(JSONType, default=dict)

    vehicle = relationship("Vehicle", back_populates="state")
