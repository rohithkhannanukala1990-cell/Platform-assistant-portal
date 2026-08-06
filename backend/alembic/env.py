"""Alembic environment — wired to the SQLModel metadata of the backend.

Usage (from the repo root):

    alembic -c backend/alembic.ini upgrade head     # apply migrations
    alembic -c backend/alembic.ini revision --autogenerate -m "add foo column"

The database URL comes from the DATABASE_URL environment variable (same
variable the app uses); it falls back to the sqlalchemy.url in alembic.ini
(local SQLite).

Existing databases that were created by SQLModel.metadata.create_all should
be marked as already migrated once:

    alembic -c backend/alembic.ini stamp head
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make `backend` importable when alembic is invoked from anywhere.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlmodel import SQLModel  # noqa: E402

from backend.db.core import DATABASE_URL, _import_models  # noqa: E402

_import_models()

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# DATABASE_URL env (normalised by backend.db.core) wins over alembic.ini.
if os.getenv("DATABASE_URL"):
    config.set_main_option("sqlalchemy.url", DATABASE_URL)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=url.startswith("sqlite"),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Batch mode so ALTERs work on SQLite dev databases too.
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
