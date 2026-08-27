from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey
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
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    altitude: Mapped[float | None] = mapped_column(Float)
    gps_speed: Mapped[float | None] = mapped_column(Float)
    heading: Mapped[float | None] = mapped_column(Float)
    accuracy: Mapped[float | None] = mapped_column(Float)
    latest_metrics: Mapped[JSONValue] = mapped_column(JSONType, default=dict)
    device_state: Mapped[JSONValue] = mapped_column(JSONType, default=dict)

    vehicle = relationship("Vehicle", back_populates="state")
