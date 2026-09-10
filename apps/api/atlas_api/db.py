"""Database session management."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Generator, Optional

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings
from .models import Base  # noqa: F401  (imported for its side effect: model registration)

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"

logger = logging.getLogger("atlas.db")

_settings = get_settings()

_engine_kwargs: dict = {"echo": _settings.database_echo, "future": True}
if _settings.uses_sqlite:
    # SQLite is the zero-setup fallback for local development and tests.
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    _engine_kwargs.update(pool_pre_ping=True, pool_size=5, max_overflow=10)

engine: Engine = create_engine(_settings.atlas_database_url, **_engine_kwargs)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@event.listens_for(Engine, "connect")
def _enforce_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
    """SQLite ignores foreign keys unless asked not to.

    Without this, cascade deletes silently do nothing on the development
    database and behave correctly on PostgreSQL — the worst kind of difference
    between environments.
    """
    if type(dbapi_connection).__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def init_db() -> None:
    """Bring the database up to the current migration head.

    This used to call ``Base.metadata.create_all()``, which creates missing
    tables and silently does nothing about existing ones. A column added to a
    model therefore never reached a database that already had the table, and
    the failure surfaced much later as ``no such column`` from inside an
    unrelated query. The e2e suite hit exactly that.

    Alembic is the fix: it knows which revisions a database has received and
    applies the ones it has not, altering existing tables as well as creating
    new ones.

    Deployments should still run ``make db-upgrade`` as an explicit step rather
    than relying on this. Migrating from application startup is fine for one
    process and wrong for several starting at once.
    """
    applied = upgrade_to_head()
    if applied:
        logger.warning(
            "applied %d migration(s) at startup on %s — deployments should run "
            "`make db-upgrade` as an explicit step instead",
            applied,
            _redacted_url(),
        )
    logger.info("database ready: %s", _redacted_url())


def current_revision() -> Optional[str]:
    """The revision this database is stamped at, or None if it has never been."""
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def head_revision() -> str:
    """The newest revision in the migration history."""
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def alembic_config() -> Config:
    """Alembic configured to talk to the same database the application does.

    The URL is passed explicitly rather than read from alembic.ini, so a
    migration can never be applied to a different database than the one this
    process is using.
    """
    config = Config(str(ALEMBIC_INI))
    config.cmd_opts = argparse.Namespace(x=[f"url={_settings.atlas_database_url}"])
    return config


def upgrade_to_head() -> int:
    """Apply every revision this database has not received. Returns how many."""
    before = current_revision()
    if before == head_revision():
        return 0
    command.upgrade(alembic_config(), "head")
    return 0 if before == current_revision() else 1


def _redacted_url() -> str:
    url = _settings.atlas_database_url
    if "@" in url and "//" in url:
        scheme, rest = url.split("//", 1)
        return f"{scheme}//***@{rest.split('@', 1)[1]}"
    return url


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
