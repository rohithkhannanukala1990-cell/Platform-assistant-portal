"""Add editor_files and editor_pr_approvals.

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-08-09 04:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision = "d9e0f1a2b3c4"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "editor_files",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("tenant_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("workspace_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("owner_username", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("filename", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("language", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("source_repo", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("source_path", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("source_ref", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("source_sha", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("editor_files", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_editor_files_tenant_id"), ["tenant_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_editor_files_workspace_id"), ["workspace_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_editor_files_owner_username"), ["owner_username"], unique=False)

    op.create_table(
        "editor_pr_approvals",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("tenant_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("username", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("file_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("repo", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("path", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("branch_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("base_branch", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("base_sha", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("idempotency_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("agent_run_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("pr_url", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("pr_number", sa.Integer(), nullable=True),
        sa.Column("decided_by", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("error", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("editor_pr_approvals", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_editor_pr_approvals_tenant_id"), ["tenant_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_editor_pr_approvals_username"), ["username"], unique=False)
        batch_op.create_index(batch_op.f("ix_editor_pr_approvals_file_id"), ["file_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_editor_pr_approvals_idempotency_key"), ["idempotency_key"], unique=False)
        batch_op.create_index(batch_op.f("ix_editor_pr_approvals_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_editor_pr_approvals_agent_run_id"), ["agent_run_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("editor_pr_approvals", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_editor_pr_approvals_agent_run_id"))
        batch_op.drop_index(batch_op.f("ix_editor_pr_approvals_status"))
        batch_op.drop_index(batch_op.f("ix_editor_pr_approvals_idempotency_key"))
        batch_op.drop_index(batch_op.f("ix_editor_pr_approvals_file_id"))
        batch_op.drop_index(batch_op.f("ix_editor_pr_approvals_username"))
        batch_op.drop_index(batch_op.f("ix_editor_pr_approvals_tenant_id"))
    op.drop_table("editor_pr_approvals")
    with op.batch_alter_table("editor_files", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_editor_files_owner_username"))
        batch_op.drop_index(batch_op.f("ix_editor_files_workspace_id"))
        batch_op.drop_index(batch_op.f("ix_editor_files_tenant_id"))
    op.drop_table("editor_files")
