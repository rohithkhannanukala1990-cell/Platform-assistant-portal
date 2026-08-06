"""Add llm_usage_events for org token cost reporting.

Revision ID: a1b2c3d4e5f6
Revises: 229e9bd18322
Create Date: 2026-08-06 16:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision = "a1b2c3d4e5f6"
down_revision = "229e9bd18322"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_usage_events",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("tenant_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("workspace_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("source", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("provider", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("model", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("config_id", sa.Integer(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("request_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("llm_usage_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_llm_usage_events_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_llm_usage_events_tenant_id"), ["tenant_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_llm_usage_events_workspace_id"), ["workspace_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_llm_usage_events_user_id"), ["user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_llm_usage_events_source"), ["source"], unique=False)
        batch_op.create_index(batch_op.f("ix_llm_usage_events_provider"), ["provider"], unique=False)
        batch_op.create_index(batch_op.f("ix_llm_usage_events_model"), ["model"], unique=False)
        batch_op.create_index(batch_op.f("ix_llm_usage_events_config_id"), ["config_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("llm_usage_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_llm_usage_events_config_id"))
        batch_op.drop_index(batch_op.f("ix_llm_usage_events_model"))
        batch_op.drop_index(batch_op.f("ix_llm_usage_events_provider"))
        batch_op.drop_index(batch_op.f("ix_llm_usage_events_source"))
        batch_op.drop_index(batch_op.f("ix_llm_usage_events_user_id"))
        batch_op.drop_index(batch_op.f("ix_llm_usage_events_workspace_id"))
        batch_op.drop_index(batch_op.f("ix_llm_usage_events_tenant_id"))
        batch_op.drop_index(batch_op.f("ix_llm_usage_events_created_at"))
    op.drop_table("llm_usage_events")
