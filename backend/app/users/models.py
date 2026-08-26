from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.common.ids import new_id
from backend.app.common.models import Base, TimestampMixin
from backend.app.common.types import JSONType, JSONValue


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    permissions: Mapped[JSONValue] = mapped_column(JSONType, default=dict)

    # Both foreign keys cascade in the database. Without passive_deletes the ORM
    # would first try to null them, which their NOT NULL columns reject, so an
    # account could never actually be removed.
    identities = relationship(
        "AuthenticationIdentity", back_populates="user", passive_deletes="all"
    )
    vehicles = relationship("Vehicle", back_populates="owner", passive_deletes="all")
