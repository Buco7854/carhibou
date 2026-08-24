"""remove vehicle propulsion classification

Revision ID: 91c5e8a3f204
Revises: 83b4c7d9e1f2
Create Date: 2026-08-24 19:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "91c5e8a3f204"
down_revision: str | Sequence[str] | None = "83b4c7d9e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("vehicles") as batch_op:
        batch_op.drop_column("propulsion_type")


def downgrade() -> None:
    with op.batch_alter_table("vehicles") as batch_op:
        batch_op.add_column(
            sa.Column(
                "propulsion_type",
                sa.String(length=30),
                nullable=False,
                server_default="unknown",
            )
        )
