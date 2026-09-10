"""Shared plumbing for the PostgreSQL-backed test modules.

Three modules now build throwaway databases — schema, RLS and migrations — and
the create/drop dance is fiddly enough that three copies of it would drift.

Not a conftest: these are plain helpers, not fixtures, and importing them by
name makes it obvious where the behaviour lives.
"""

from __future__ import annotations

import argparse
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")

POSTGRES_URL = os.getenv("ATLAS_TEST_POSTGRES_URL")
API_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = API_ROOT / "alembic.ini"
SHIM = Path(__file__).resolve().parent / "sql" / "supabase_auth_shim.sql"

# Alembic connects through SQLAlchemy, which needs the driver named; psycopg
# connects directly, which does not.
def as_sqlalchemy_url(url: str) -> str:
    return url.replace("postgresql://", "postgresql+psycopg://")


def server_reachable() -> bool:
    if not POSTGRES_URL:
        return False
    try:
        with psycopg.connect(POSTGRES_URL, connect_timeout=3):
            return True
    except Exception:
        return False


def alembic_config(url: str):
    """Alembic pointed at one specific database.

    The URL goes through `-x url=`, the same route a human uses, so the tests
    exercise the configuration path rather than a private one.
    """
    from alembic.config import Config

    config = Config(str(ALEMBIC_INI))
    config.cmd_opts = argparse.Namespace(x=[f"url={as_sqlalchemy_url(url)}"])
    return config


def _drop_database(name: str) -> None:
    """Drop a throwaway database, tolerating a slow-to-close client.

    `WITH (FORCE)` terminates other backends, which fails outright if one of
    them is a superuser-owned autovacuum worker. So: terminate the connections
    this role actually owns, then drop, then retry briefly.
    """
    with psycopg.connect(POSTGRES_URL, autocommit=True) as admin:
        admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
            " WHERE datname = %s AND pid <> pg_backend_pid()"
            " AND usename = current_user",
            (name,),
        )
        for attempt in range(5):
            try:
                admin.execute(f'DROP DATABASE IF EXISTS "{name}"')
                return
            except psycopg.errors.ObjectInUse:
                if attempt == 4:
                    raise
                time.sleep(0.2)


@contextmanager
def throwaway_database(prefix: str = "atlas_test"):
    """Create an empty database, yield its URL, and drop it afterwards."""
    name = f"{prefix}_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(POSTGRES_URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    try:
        yield POSTGRES_URL.rsplit("/", 1)[0] + f"/{name}"
    finally:
        _drop_database(name)


def install_auth_shim(url: str) -> None:
    """Give a vanilla PostgreSQL database an auth.uid().

    See tests/sql/supabase_auth_shim.sql for what this does and does not prove.
    """
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(SHIM.read_text())
