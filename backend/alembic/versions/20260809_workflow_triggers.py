"""Add workflow trigger guardrail columns.

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-08-09 04:30:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision = "e0f1a2b3c4d5"
down_revision = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workflow_definitions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("first_live_run_approved_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "on_concurrent_limit",
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=False,
                server_default="drop",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("workflow_definitions", schema=None) as batch_op:
        batch_op.drop_column("on_concurrent_limit")
        batch_op.drop_column("first_live_run_approved_at")
