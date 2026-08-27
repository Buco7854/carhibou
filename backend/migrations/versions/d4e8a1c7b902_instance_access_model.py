"""replace ownership with instance and vehicle access

Revision ID: d4e8a1c7b902
Revises: a7f31c9d5e80
Create Date: 2026-08-26 23:30:00.000000
"""

from collections.abc import Sequence
import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d4e8a1c7b902"
down_revision: str | Sequence[str] | None = "a7f31c9d5e80"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def _normalize_permissions() -> None:
    bind = op.get_bind()
    users = sa.table(
        "users",
        sa.column("id", sa.String(length=36)),
        sa.column("permissions", JSON),
    )
    for user_id, raw_permissions in bind.execute(sa.select(users.c.id, users.c.permissions)):
        permissions = raw_permissions
        if isinstance(permissions, str):
            permissions = json.loads(permissions)
        normalized = {"system.admin": True} if permissions.get("system.admin") else {}
        bind.execute(
            users.update().where(users.c.id == user_id).values(permissions=normalized)
        )


def _rename_audit_column(table: str, old: str, old_fk: str) -> None:
    with op.batch_alter_table(table) as batch_op:
        batch_op.drop_constraint(old_fk, type_="foreignkey")
        batch_op.drop_index(f"ix_{table}_{old}")
        batch_op.alter_column(
            old,
            new_column_name="created_by",
            existing_type=sa.String(length=36),
            nullable=True,
        )
    with op.batch_alter_table(table) as batch_op:
        batch_op.create_foreign_key(
            f"fk_{table}_created_by_users",
            "users",
            ["created_by"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(f"ix_{table}_created_by", table, ["created_by"], unique=False)


def _deduplicate_secrets() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, name FROM secrets "
            "ORDER BY name, updated_at DESC, id DESC"
        )
    ).mappings()
    seen: set[str] = set()
    for row in rows:
        name = str(row["name"])
        if name in seen:
            bind.execute(sa.text("DELETE FROM secrets WHERE id = :id"), {"id": row["id"]})
        else:
            seen.add(name)


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "can_create_profiles", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
    _normalize_permissions()

    op.create_table(
        "vehicle_access_grants",
        sa.Column("vehicle_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("level", sa.String(length=10), nullable=False),
        sa.CheckConstraint(
            "level IN ('view', 'operate')",
            name=op.f("ck_vehicle_access_grants_vehicle_access_level"),
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name=op.f("fk_vehicle_access_grants_vehicle_id_vehicles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_vehicle_access_grants_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "vehicle_id", "user_id", name=op.f("pk_vehicle_access_grants")
        ),
    )
    op.create_index(
        op.f("ix_vehicle_access_grants_user_id"),
        "vehicle_access_grants",
        ["user_id"],
        unique=False,
    )
    op.execute(
        sa.text(
            "INSERT INTO vehicle_access_grants (vehicle_id, user_id, level) "
            "SELECT id, owner_id, 'operate' FROM vehicles"
        )
    )

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("value", JSON, nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_app_settings")),
    )

    _rename_audit_column("vehicles", "owner_id", "fk_vehicles_owner_id_users")
    _rename_audit_column(
        "vehicle_profiles", "owner_id", "fk_vehicle_profiles_owner_id_users"
    )
    _rename_audit_column("hooks", "owner_id", "fk_hooks_owner_id_users")

    _deduplicate_secrets()
    with op.batch_alter_table("secrets") as batch_op:
        batch_op.drop_constraint("uq_secrets_owner_id", type_="unique")
        batch_op.drop_constraint("fk_secrets_owner_id_users", type_="foreignkey")
        batch_op.drop_index("ix_secrets_owner_id")
        batch_op.drop_column("owner_id")
        batch_op.create_unique_constraint("uq_secrets_name", ["name"])


def _fallback_user_id() -> str | None:
    value = op.get_bind().scalar(sa.text("SELECT id FROM users ORDER BY created_at LIMIT 1"))
    return str(value) if value is not None else None


def _restore_owner_column(table: str) -> None:
    fallback = _fallback_user_id()
    with op.batch_alter_table(table) as batch_op:
        batch_op.drop_constraint(f"fk_{table}_created_by_users", type_="foreignkey")
        batch_op.drop_index(f"ix_{table}_created_by")
        batch_op.alter_column(
            "created_by",
            new_column_name="owner_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )
    if fallback:
        op.execute(
            sa.text(f"UPDATE {table} SET owner_id = :owner WHERE owner_id IS NULL").bindparams(
                owner=fallback
            )
        )
    with op.batch_alter_table(table) as batch_op:
        batch_op.alter_column(
            "owner_id", existing_type=sa.String(length=36), nullable=False
        )
        batch_op.create_foreign_key(
            f"fk_{table}_owner_id_users",
            "users",
            ["owner_id"],
            ["id"],
            ondelete="CASCADE",
        )
    op.create_index(f"ix_{table}_owner_id", table, ["owner_id"], unique=False)


def downgrade() -> None:
    fallback = _fallback_user_id()
    with op.batch_alter_table("secrets") as batch_op:
        batch_op.drop_constraint("uq_secrets_name", type_="unique")
        batch_op.add_column(sa.Column("owner_id", sa.String(length=36), nullable=True))
    if fallback:
        op.execute(sa.text("UPDATE secrets SET owner_id = :owner").bindparams(owner=fallback))
    with op.batch_alter_table("secrets") as batch_op:
        batch_op.alter_column(
            "owner_id", existing_type=sa.String(length=36), nullable=False
        )
        batch_op.create_foreign_key(
            "fk_secrets_owner_id_users",
            "users",
            ["owner_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index("ix_secrets_owner_id", ["owner_id"], unique=False)
        batch_op.create_unique_constraint("uq_secrets_owner_id", ["owner_id", "name"])

    _restore_owner_column("hooks")
    _restore_owner_column("vehicle_profiles")
    _restore_owner_column("vehicles")

    op.drop_table("app_settings")
    op.drop_index(
        op.f("ix_vehicle_access_grants_user_id"), table_name="vehicle_access_grants"
    )
    op.drop_table("vehicle_access_grants")

    bind = op.get_bind()
    users = sa.table(
        "users",
        sa.column("id", sa.String(length=36)),
        sa.column("permissions", JSON),
    )
    for user_id, raw_permissions in bind.execute(sa.select(users.c.id, users.c.permissions)):
        permissions = raw_permissions
        if isinstance(permissions, str):
            permissions = json.loads(permissions)
        if permissions.get("system.admin"):
            permissions = {"hooks.manage_code": True, "system.admin": True}
        bind.execute(
            users.update().where(users.c.id == user_id).values(permissions=permissions)
        )
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("can_create_profiles")
