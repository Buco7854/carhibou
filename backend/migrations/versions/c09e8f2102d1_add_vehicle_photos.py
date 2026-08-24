"""add vehicle photos

Revision ID: c09e8f2102d1
Revises: 4b4d1dbd6026
Create Date: 2026-08-24 13:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c09e8f2102d1"
down_revision: str | Sequence[str] | None = "4b4d1dbd6026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vehicle_photos",
        sa.Column("vehicle_id", sa.String(length=36), nullable=False),
        sa.Column("media_type", sa.String(length=20), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("etag", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name=op.f("fk_vehicle_photos_vehicle_id_vehicles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("vehicle_id", name=op.f("pk_vehicle_photos")),
    )


def downgrade() -> None:
    op.drop_table("vehicle_photos")
