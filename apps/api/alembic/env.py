"""Alembic environment for Atlas.

Two decisions here are load-bearing.

**The URL comes from Atlas's own settings, not from alembic.ini.** A migration
runner pointed at a different database than the application is worse than no
runner at all: it reports success while the running system is untouched. So
``ATLAS_DATABASE_URL`` is the single source of truth, exactly as it is for the
API. ``-x url=...`` overrides it for a deliberate one-off.

**SQLite gets batch mode.** Atlas falls back to SQLite when no PostgreSQL is
configured, and SQLite cannot ``ALTER TABLE`` in most of the ways a migration
needs. Batch mode makes Alembic rebuild the table instead, so the same revision
file works on both engines rather than silently only working on one.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# The API package lives beside this directory. Adding it explicitly means
# `alembic -c apps/api/alembic.ini ...` works from the repository root, not
# only from apps/api.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas_api.config import get_settings  # noqa: E402
from atlas_api.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    """`-x url=...` beats ATLAS_DATABASE_URL beats the SQLite fallback."""
    override = context.get_x_argument(as_dictionary=True).get("url")
    if override:
        return override
    return get_settings().atlas_database_url


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it.

    `alembic upgrade head --sql` produces a script a DBA can review and apply
    by hand, which is how a change reaches a database nobody lets a CI job
    connect to.
    """
    url = _database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=_is_sqlite(url),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _database_url()
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = url

    connectable = engine_from_config(
        section, prefix="sqlalchemy.", poolclass=pool.NullPool
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Without compare_type, `alembic check` misses a column whose type
            # changed — which is most of the ways a schema drifts in practice.
            compare_type=True,
            render_as_batch=_is_sqlite(url),
        )
        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
