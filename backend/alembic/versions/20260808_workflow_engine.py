"""Add workflow_definitions and workflow_runs tables.

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-08-08 21:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision = "b7c8d9e0f1a2"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_definitions",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("tenant_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("workspace_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("steps_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("trigger_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("trigger_config_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("risk", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("max_runs_per_hour", sa.Integer(), nullable=False),
        sa.Column("max_concurrent_runs", sa.Integer(), nullable=False),
        sa.Column("created_by", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("workflow_definitions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_workflow_definitions_tenant_id"), ["tenant_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_workflow_definitions_workspace_id"), ["workspace_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_workflow_definitions_name"), ["name"], unique=False)

    op.create_table(
        "workflow_runs",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("tenant_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("workflow_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("current_step_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("context_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("steps_state_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("triggered_by", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("grounding", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("error", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("workflow_runs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_workflow_runs_tenant_id"), ["tenant_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_workflow_runs_workflow_id"), ["workflow_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_workflow_runs_status"), ["status"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("workflow_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_workflow_runs_status"))
        batch_op.drop_index(batch_op.f("ix_workflow_runs_workflow_id"))
        batch_op.drop_index(batch_op.f("ix_workflow_runs_tenant_id"))
    op.drop_table("workflow_runs")

    with op.batch_alter_table("workflow_definitions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_workflow_definitions_name"))
        batch_op.drop_index(batch_op.f("ix_workflow_definitions_workspace_id"))
        batch_op.drop_index(batch_op.f("ix_workflow_definitions_tenant_id"))
    op.drop_table("workflow_definitions")
