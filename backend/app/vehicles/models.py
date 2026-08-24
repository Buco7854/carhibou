from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.common.ids import new_id
from backend.app.common.models import Base, TimestampMixin
from backend.app.common.types import JSONType, JSONValue


class Vehicle(TimestampMixin, Base):
    __tablename__ = "vehicles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    manufacturer: Mapped[str] = mapped_column(String(120), default="")
    model: Mapped[str] = mapped_column(String(120), default="")
    year: Mapped[int | None] = mapped_column(Integer)
    vin: Mapped[str | None] = mapped_column(String(17))
    propulsion_type: Mapped[str] = mapped_column(String(30), default="unknown")
    battery_nominal_capacity_kwh: Mapped[float | None] = mapped_column(Float)
    vehicle_profile: Mapped[str | None] = mapped_column(String(120))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    display_preferences: Mapped[JSONValue] = mapped_column(JSONType, default=dict)
    color: Mapped[str] = mapped_column(String(20), default="#62d4a7")
    icon: Mapped[str] = mapped_column(String(50), default="car")

    owner = relationship("User", back_populates="vehicles")
    devices = relationship("Device", back_populates="vehicle")
    state = relationship("VehicleState", back_populates="vehicle", uselist=False)
