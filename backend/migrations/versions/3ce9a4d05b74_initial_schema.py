"""initial schema

Revision ID: 3ce9a4d05b74
Revises:
Create Date: 2026-08-27 05:57:26.770159
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "3ce9a4d05b74"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column(
            "value",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_app_settings")),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("type", sa.String(length=80), nullable=False),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )
    op.create_index(op.f("ix_jobs_status"), "jobs", ["status"], unique=False)
    op.create_index(op.f("ix_jobs_type"), "jobs", ["type"], unique=False)
    op.create_table(
        "secrets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_secrets")),
        sa.UniqueConstraint("name", name=op.f("uq_secrets_name")),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("can_create_profiles", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "permissions",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_id", sa.String(length=120), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("worker_id", name=op.f("pk_worker_heartbeats")),
    )
    op.create_index(
        op.f("ix_worker_heartbeats_seen_at"), "worker_heartbeats", ["seen_at"], unique=False
    )
    op.create_table(
        "auth_identities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("subject", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_auth_identities_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_identities")),
        sa.UniqueConstraint("provider", "subject", name=op.f("uq_auth_identities_provider")),
    )
    op.create_index(
        op.f("ix_auth_identities_user_id"), "auth_identities", ["user_id"], unique=False
    )
    op.create_table(
        "dashboards",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column(
            "layout",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_dashboards_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dashboards")),
    )
    op.create_index(op.f("ix_dashboards_owner_id"), "dashboards", ["owner_id"], unique=False)
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_sessions_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
    )
    op.create_index(op.f("ix_sessions_expires_at"), "sessions", ["expires_at"], unique=False)
    op.create_index(op.f("ix_sessions_token_hash"), "sessions", ["token_hash"], unique=True)
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)
    op.create_table(
        "vehicle_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
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
            ["created_by"],
            ["users.id"],
            name=op.f("fk_vehicle_profiles_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vehicle_profiles")),
    )
    op.create_index(
        op.f("ix_vehicle_profiles_created_by"), "vehicle_profiles", ["created_by"], unique=False
    )
    op.create_table(
        "vehicles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("manufacturer", sa.String(length=120), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("vin", sa.String(length=17), nullable=True),
        sa.Column("battery_nominal_capacity_kwh", sa.Float(), nullable=True),
        sa.Column("vehicle_profile", sa.String(length=120), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column(
            "display_preferences",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("color", sa.String(length=20), nullable=False),
        sa.Column("icon", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_vehicles_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vehicles")),
    )
    op.create_index(op.f("ix_vehicles_created_by"), "vehicles", ["created_by"], unique=False)
    op.create_table(
        "agent_enrollment_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("vehicle_id", sa.String(length=36), nullable=False),
        sa.Column("intended_name", sa.String(length=120), nullable=False),
        sa.Column("implementation_id", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sampling_seconds", sa.Integer(), server_default="5", nullable=False),
        sa.Column("upload_seconds", sa.Integer(), server_default="30", nullable=False),
        sa.Column("parked_sampling_seconds", sa.Integer(), server_default="5", nullable=False),
        sa.Column("parked_upload_seconds", sa.Integer(), server_default="30", nullable=False),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name=op.f("fk_agent_enrollment_tokens_vehicle_id_vehicles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_enrollment_tokens")),
    )
    op.create_index(
        op.f("ix_agent_enrollment_tokens_expires_at"),
        "agent_enrollment_tokens",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_enrollment_tokens_token_hash"),
        "agent_enrollment_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_agent_enrollment_tokens_vehicle_id"),
        "agent_enrollment_tokens",
        ["vehicle_id"],
        unique=False,
    )
    op.create_table(
        "agents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("vehicle_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("credential_hash", sa.String(length=64), nullable=False),
        sa.Column("credential_version", sa.Integer(), nullable=False),
        sa.Column("implementation_id", sa.String(length=100), nullable=False),
        sa.Column("protocol_version", sa.Integer(), nullable=False),
        sa.Column("agent_version", sa.String(length=50), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=True),
        sa.Column(
            "hardware",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_config_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("config_version", sa.Integer(), nullable=False),
        sa.Column("sampling_seconds", sa.Integer(), server_default="5", nullable=False),
        sa.Column("upload_seconds", sa.Integer(), server_default="30", nullable=False),
        sa.Column("parked_sampling_seconds", sa.Integer(), server_default="5", nullable=False),
        sa.Column("parked_upload_seconds", sa.Integer(), server_default="30", nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name=op.f("fk_agents_vehicle_id_vehicles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agents")),
    )
    op.create_index(op.f("ix_agents_credential_hash"), "agents", ["credential_hash"], unique=True)
    op.create_index(op.f("ix_agents_last_seen_at"), "agents", ["last_seen_at"], unique=False)
    op.create_index(op.f("ix_agents_vehicle_id"), "agents", ["vehicle_id"], unique=False)
    op.create_table(
        "connectors",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("vehicle_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "config",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("encrypted_password", sa.Text(), nullable=True),
        sa.Column("config_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("last_connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sample_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name=op.f("fk_connectors_vehicle_id_vehicles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_connectors")),
    )
    op.create_index(op.f("ix_connectors_vehicle_id"), "connectors", ["vehicle_id"], unique=False)
    op.create_table(
        "hooks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("vehicle_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("trigger_type", sa.String(length=80), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_hooks_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name=op.f("fk_hooks_vehicle_id_vehicles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hooks")),
    )
    op.create_index(op.f("ix_hooks_created_by"), "hooks", ["created_by"], unique=False)
    op.create_index(op.f("ix_hooks_vehicle_id"), "hooks", ["vehicle_id"], unique=False)
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
            ["user_id"],
            ["users.id"],
            name=op.f("fk_vehicle_access_grants_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name=op.f("fk_vehicle_access_grants_vehicle_id_vehicles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("vehicle_id", "user_id", name=op.f("pk_vehicle_access_grants")),
    )
    op.create_index(
        op.f("ix_vehicle_access_grants_user_id"), "vehicle_access_grants", ["user_id"], unique=False
    )
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
    op.create_table(
        "hook_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("hook_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_hook_revisions_created_by_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["hook_id"],
            ["hooks.id"],
            name=op.f("fk_hook_revisions_hook_id_hooks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hook_revisions")),
        sa.UniqueConstraint("hook_id", "revision", name=op.f("uq_hook_revisions_hook_id")),
    )
    op.create_index(op.f("ix_hook_revisions_hook_id"), "hook_revisions", ["hook_id"], unique=False)
    op.create_table(
        "hook_state",
        sa.Column("hook_id", sa.String(length=36), nullable=False),
        sa.Column(
            "value",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["hook_id"], ["hooks.id"], name=op.f("fk_hook_state_hook_id_hooks"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("hook_id", name=op.f("pk_hook_state")),
    )
    op.create_table(
        "telemetry",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("vehicle_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("boot_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("altitude", sa.Float(), nullable=True),
        sa.Column("gps_speed", sa.Float(), nullable=True),
        sa.Column("heading", sa.Float(), nullable=True),
        sa.Column("accuracy", sa.Float(), nullable=True),
        sa.Column(
            "metrics",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "agent_data",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            name=op.f("fk_telemetry_agent_id_agents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name=op.f("fk_telemetry_vehicle_id_vehicles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_telemetry")),
    )
    op.create_index(
        "ix_telemetry_agent_recorded", "telemetry", ["agent_id", "recorded_at"], unique=False
    )
    op.create_index(
        "ix_telemetry_vehicle_recorded", "telemetry", ["vehicle_id", "recorded_at"], unique=False
    )
    op.create_table(
        "triggers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("type", sa.String(length=80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("vehicle_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("telemetry_id", sa.String(length=36), nullable=True),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            name=op.f("fk_triggers_agent_id_agents"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["telemetry_id"],
            ["telemetry.id"],
            name=op.f("fk_triggers_telemetry_id_telemetry"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name=op.f("fk_triggers_vehicle_id_vehicles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_triggers")),
    )
    op.create_index(op.f("ix_triggers_occurred_at"), "triggers", ["occurred_at"], unique=False)
    op.create_index(op.f("ix_triggers_telemetry_id"), "triggers", ["telemetry_id"], unique=False)
    op.create_index(op.f("ix_triggers_type"), "triggers", ["type"], unique=False)
    op.create_index(op.f("ix_triggers_vehicle_id"), "triggers", ["vehicle_id"], unique=False)
    op.create_table(
        "vehicle_state",
        sa.Column("vehicle_id", sa.String(length=36), nullable=False),
        sa.Column("telemetry_id", sa.String(length=36), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("altitude", sa.Float(), nullable=True),
        sa.Column("gps_speed", sa.Float(), nullable=True),
        sa.Column("heading", sa.Float(), nullable=True),
        sa.Column("accuracy", sa.Float(), nullable=True),
        sa.Column(
            "latest_metrics",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "agent_state",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["telemetry_id"],
            ["telemetry.id"],
            name=op.f("fk_vehicle_state_telemetry_id_telemetry"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name=op.f("fk_vehicle_state_vehicle_id_vehicles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("vehicle_id", name=op.f("pk_vehicle_state")),
    )
    op.create_index(
        op.f("ix_vehicle_state_updated_at"), "vehicle_state", ["updated_at"], unique=False
    )
    op.create_table(
        "hook_executions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("hook_id", sa.String(length=36), nullable=False),
        sa.Column("trigger_id", sa.String(length=36), nullable=False),
        sa.Column("telemetry_id", sa.String(length=36), nullable=True),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column(
            "logs",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["hook_id"],
            ["hooks.id"],
            name=op.f("fk_hook_executions_hook_id_hooks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["telemetry_id"],
            ["telemetry.id"],
            name=op.f("fk_hook_executions_telemetry_id_telemetry"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["trigger_id"],
            ["triggers.id"],
            name=op.f("fk_hook_executions_trigger_id_triggers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hook_executions")),
    )
    op.create_index(
        op.f("ix_hook_executions_hook_id"), "hook_executions", ["hook_id"], unique=False
    )
    op.create_index(op.f("ix_hook_executions_status"), "hook_executions", ["status"], unique=False)
    op.create_index(
        op.f("ix_hook_executions_telemetry_id"), "hook_executions", ["telemetry_id"], unique=False
    )
    op.create_index(
        op.f("ix_hook_executions_trigger_id"), "hook_executions", ["trigger_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_hook_executions_trigger_id"), table_name="hook_executions")
    op.drop_index(op.f("ix_hook_executions_telemetry_id"), table_name="hook_executions")
    op.drop_index(op.f("ix_hook_executions_status"), table_name="hook_executions")
    op.drop_index(op.f("ix_hook_executions_hook_id"), table_name="hook_executions")
    op.drop_table("hook_executions")
    op.drop_index(op.f("ix_vehicle_state_updated_at"), table_name="vehicle_state")
    op.drop_table("vehicle_state")
    op.drop_index(op.f("ix_triggers_vehicle_id"), table_name="triggers")
    op.drop_index(op.f("ix_triggers_type"), table_name="triggers")
    op.drop_index(op.f("ix_triggers_telemetry_id"), table_name="triggers")
    op.drop_index(op.f("ix_triggers_occurred_at"), table_name="triggers")
    op.drop_table("triggers")
    op.drop_index("ix_telemetry_vehicle_recorded", table_name="telemetry")
    op.drop_index("ix_telemetry_agent_recorded", table_name="telemetry")
    op.drop_table("telemetry")
    op.drop_table("hook_state")
    op.drop_index(op.f("ix_hook_revisions_hook_id"), table_name="hook_revisions")
    op.drop_table("hook_revisions")
    op.drop_table("vehicle_photos")
    op.drop_index(op.f("ix_vehicle_access_grants_user_id"), table_name="vehicle_access_grants")
    op.drop_table("vehicle_access_grants")
    op.drop_index(op.f("ix_hooks_vehicle_id"), table_name="hooks")
    op.drop_index(op.f("ix_hooks_created_by"), table_name="hooks")
    op.drop_table("hooks")
    op.drop_index(op.f("ix_connectors_vehicle_id"), table_name="connectors")
    op.drop_table("connectors")
    op.drop_index(op.f("ix_agents_vehicle_id"), table_name="agents")
    op.drop_index(op.f("ix_agents_last_seen_at"), table_name="agents")
    op.drop_index(op.f("ix_agents_credential_hash"), table_name="agents")
    op.drop_table("agents")
    op.drop_index(
        op.f("ix_agent_enrollment_tokens_vehicle_id"), table_name="agent_enrollment_tokens"
    )
    op.drop_index(
        op.f("ix_agent_enrollment_tokens_token_hash"), table_name="agent_enrollment_tokens"
    )
    op.drop_index(
        op.f("ix_agent_enrollment_tokens_expires_at"), table_name="agent_enrollment_tokens"
    )
    op.drop_table("agent_enrollment_tokens")
    op.drop_index(op.f("ix_vehicles_created_by"), table_name="vehicles")
    op.drop_table("vehicles")
    op.drop_index(op.f("ix_vehicle_profiles_created_by"), table_name="vehicle_profiles")
    op.drop_table("vehicle_profiles")
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_token_hash"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_expires_at"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_index(op.f("ix_dashboards_owner_id"), table_name="dashboards")
    op.drop_table("dashboards")
    op.drop_index(op.f("ix_auth_identities_user_id"), table_name="auth_identities")
    op.drop_table("auth_identities")
    op.drop_index(op.f("ix_worker_heartbeats_seen_at"), table_name="worker_heartbeats")
    op.drop_table("worker_heartbeats")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
    op.drop_table("secrets")
    op.drop_index(op.f("ix_jobs_type"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_status"), table_name="jobs")
    op.drop_table("jobs")
    op.drop_table("app_settings")
