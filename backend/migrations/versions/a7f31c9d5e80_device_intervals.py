"""per-device sampling and upload intervals

Revision ID: a7f31c9d5e80
Revises: 91c5e8a3f204
Create Date: 2026-08-26 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7f31c9d5e80"
down_revision: str | Sequence[str] | None = "91c5e8a3f204"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The values every tracker was served before these columns existed, so an
# existing deployment keeps the cadence it already had.
SAMPLING_SECONDS = 5
UPLOAD_SECONDS = 30


def upgrade() -> None:
    for table in ("devices", "device_enrollment_tokens"):
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "sampling_seconds",
                    sa.Integer(),
                    nullable=False,
                    server_default=str(SAMPLING_SECONDS),
                )
            )
            batch_op.add_column(
                sa.Column(
                    "upload_seconds",
                    sa.Integer(),
                    nullable=False,
                    server_default=str(UPLOAD_SECONDS),
                )
            )


def downgrade() -> None:
    for table in ("device_enrollment_tokens", "devices"):
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_column("upload_seconds")
            batch_op.drop_column("sampling_seconds")
