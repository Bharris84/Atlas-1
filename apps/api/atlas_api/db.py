"""Database session management."""

from __future__ import annotations

import logging
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings
from .models import Base

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
    """Create tables that do not exist yet.

    Convenient for development and tests. Production schema changes go through
    the SQL migrations in ``database/migrations``.
    """
    Base.metadata.create_all(bind=engine)
    logger.info("database ready: %s", _redacted_url())


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
