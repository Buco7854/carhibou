"""add owner-managed vehicle profiles

Revision ID: 83b4c7d9e1f2
Revises: c09e8f2102d1
Create Date: 2026-08-24 17:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "83b4c7d9e1f2"
down_revision: str | Sequence[str] | None = "c09e8f2102d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vehicle_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=False),
        sa.Column(
            "definition",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_vehicle_profiles_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vehicle_profiles")),
    )
    op.create_index(
        op.f("ix_vehicle_profiles_owner_id"), "vehicle_profiles", ["owner_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_vehicle_profiles_owner_id"), table_name="vehicle_profiles")
    op.drop_table("vehicle_profiles")
