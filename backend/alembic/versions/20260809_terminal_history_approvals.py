"""Add terminal_history and terminal_approvals.

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-08-09 03:30:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision = "c8d9e0f1a2b3"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "terminal_history",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("tenant_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("username", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("command", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("terminal_history", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_terminal_history_tenant_id"), ["tenant_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_terminal_history_username"), ["username"], unique=False)
        batch_op.create_index(batch_op.f("ix_terminal_history_created_at"), ["created_at"], unique=False)

    op.create_table(
        "terminal_approvals",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("tenant_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("username", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("command", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("reasons_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("session_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("agent_run_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("decided_by", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("decision_reason", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("terminal_approvals", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_terminal_approvals_tenant_id"), ["tenant_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_terminal_approvals_username"), ["username"], unique=False)
        batch_op.create_index(batch_op.f("ix_terminal_approvals_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_terminal_approvals_session_id"), ["session_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_terminal_approvals_agent_run_id"), ["agent_run_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("terminal_approvals", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_terminal_approvals_agent_run_id"))
        batch_op.drop_index(batch_op.f("ix_terminal_approvals_session_id"))
        batch_op.drop_index(batch_op.f("ix_terminal_approvals_status"))
        batch_op.drop_index(batch_op.f("ix_terminal_approvals_username"))
        batch_op.drop_index(batch_op.f("ix_terminal_approvals_tenant_id"))
    op.drop_table("terminal_approvals")

    with op.batch_alter_table("terminal_history", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_terminal_history_created_at"))
        batch_op.drop_index(batch_op.f("ix_terminal_history_username"))
        batch_op.drop_index(batch_op.f("ix_terminal_history_tenant_id"))
    op.drop_table("terminal_history")
