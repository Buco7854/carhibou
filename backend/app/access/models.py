from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.common.models import Base
from backend.app.common.types import JSONType, JSONValue


class VehicleAccessGrant(Base):
    __tablename__ = "vehicle_access_grants"
    # The composite primary key is the uniqueness guarantee: one grant per
    # vehicle and user. No separate unique constraint restates it.
    __table_args__ = (CheckConstraint("level IN ('view', 'operate')", name="vehicle_access_level"),)

    vehicle_id: Mapped[str] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    level: Mapped[str] = mapped_column(String(10))


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[JSONValue] = mapped_column(JSONType)
