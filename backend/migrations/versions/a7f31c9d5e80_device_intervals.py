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
# A parked vehicle produced the same traffic as a moving one before this existed,
# so the parked columns start equal to the driving ones and change nothing until
# somebody chooses otherwise.
PARKED_SAMPLING_SECONDS = 5
PARKED_UPLOAD_SECONDS = 30


def upgrade() -> None:
    columns = {
        "sampling_seconds": SAMPLING_SECONDS,
        "upload_seconds": UPLOAD_SECONDS,
        "parked_sampling_seconds": PARKED_SAMPLING_SECONDS,
        "parked_upload_seconds": PARKED_UPLOAD_SECONDS,
    }
    for table in ("devices", "device_enrollment_tokens"):
        with op.batch_alter_table(table) as batch_op:
            for name, default in columns.items():
                batch_op.add_column(
                    sa.Column(name, sa.Integer(), nullable=False, server_default=str(default))
                )


def downgrade() -> None:
    for table in ("device_enrollment_tokens", "devices"):
        with op.batch_alter_table(table) as batch_op:
            for name in (
                "parked_upload_seconds",
                "parked_sampling_seconds",
                "upload_seconds",
                "sampling_seconds",
            ):
                batch_op.drop_column(name)
