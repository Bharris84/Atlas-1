"""Schema validation against a real PostgreSQL server.

The rest of the suite runs on SQLite, which is fine for behaviour but proves
nothing about the production engine: JSON handling, NUMERIC precision, cascade
deletes and timezone semantics all differ. These tests close that gap.

Skipped automatically when no PostgreSQL is reachable, so the default suite
still runs anywhere. Point ATLAS_TEST_POSTGRES_URL at a server to enable them:

    ATLAS_TEST_POSTGRES_URL=postgresql://atlas:atlas@127.0.0.1:5432/postgres \
        pytest tests/test_postgres_schema.py
"""

from __future__ import annotations

import os
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")

POSTGRES_URL = os.getenv("ATLAS_TEST_POSTGRES_URL")
MIGRATIONS = Path(__file__).resolve().parents[3] / "database" / "migrations"

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL, reason="ATLAS_TEST_POSTGRES_URL is not set"
)


def _server_reachable() -> bool:
    try:
        with psycopg.connect(POSTGRES_URL, connect_timeout=3):
            return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def migrated_db():
    """A database built from the SQL migrations."""
    if not _server_reachable():
        pytest.skip("PostgreSQL is not reachable")
    name = f"atlas_mig_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(POSTGRES_URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    url = POSTGRES_URL.rsplit("/", 1)[0] + f"/{name}"
    try:
        with psycopg.connect(url, autocommit=True) as conn:
            for migration in ("0001_initial_schema.sql", "0003_investor_profile.sql"):
                conn.execute((MIGRATIONS / migration).read_text())
        yield url
    finally:
        with psycopg.connect(POSTGRES_URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture(scope="module")
def orm_db():
    """A database built by SQLAlchemy's create_all()."""
    if not _server_reachable():
        pytest.skip("PostgreSQL is not reachable")
    name = f"atlas_orm_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(POSTGRES_URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    url = POSTGRES_URL.rsplit("/", 1)[0] + f"/{name}"
    try:
        from sqlalchemy import create_engine

        from atlas_api.models import Base

        engine = create_engine(url.replace("postgresql://", "postgresql+psycopg://"))
        Base.metadata.create_all(bind=engine)
        engine.dispose()
        yield url
    finally:
        with psycopg.connect(POSTGRES_URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def _columns(url: str):
    with psycopg.connect(url) as conn:
        return conn.execute(
            """
            SELECT table_name, column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, column_name
            """
        ).fetchall()


class TestMigrationApplies:
    def test_the_initial_migration_creates_every_table(self, migrated_db):
        with psycopg.connect(migrated_db) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public'"
                ).fetchall()
            }
        assert tables == {
            "user_profiles", "properties", "owners", "leads", "deal_analyses",
            "assumption_audit", "comps", "offers", "communications",
            "rehab_projects", "data_sources", "activity_log",
        }

    def test_the_investor_profile_migration_is_idempotent(self, migrated_db):
        """It must be safe to re-run against a database that already has it."""
        sql = (MIGRATIONS / "0003_investor_profile.sql").read_text()
        with psycopg.connect(migrated_db, autocommit=True) as conn:
            conn.execute(sql)
            conn.execute(sql)


class TestMigrationMatchesTheOrm:
    def test_no_drift_between_the_sql_and_the_models(self, migrated_db, orm_db):
        """The models are the source of truth; the SQL is generated from them.

        Nothing enforced that they stayed in step until this test existed.
        """
        assert _columns(migrated_db) == _columns(orm_db)


class TestPostgresSpecificBehaviour:
    def test_money_keeps_two_decimal_places(self, migrated_db):
        """NUMERIC(14,2), not a float. SQLite would not catch a regression."""
        owner = uuid.uuid4()
        with psycopg.connect(migrated_db, autocommit=True) as conn:
            pid = uuid.uuid4()
            conn.execute(
                "INSERT INTO properties (id, owner_id, address, property_status,"
                " listing_price, created_at, updated_at)"
                " VALUES (%s,%s,'1 Test St','prospect',%s, now(), now())",
                (pid, owner, Decimal("123456.789")),
            )
            stored = conn.execute(
                "SELECT listing_price FROM properties WHERE id=%s", (pid,)
            ).fetchone()[0]
        assert isinstance(stored, Decimal)
        assert stored == Decimal("123456.79")

    def test_deleting_a_property_cascades_to_its_children(self, migrated_db):
        """SQLite silently ignores foreign keys unless a PRAGMA is set, so this
        is only meaningfully proven here."""
        owner = uuid.uuid4()
        with psycopg.connect(migrated_db, autocommit=True) as conn:
            pid, cid = uuid.uuid4(), uuid.uuid4()
            conn.execute(
                "INSERT INTO properties (id, owner_id, address, property_status,"
                " created_at, updated_at) VALUES (%s,%s,'2 Test St','prospect',now(),now())",
                (pid, owner),
            )
            conn.execute(
                "INSERT INTO comps (id, property_id, address, created_at, updated_at)"
                " VALUES (%s,%s,'3 Test St', now(), now())",
                (cid, pid),
            )
            conn.execute("DELETE FROM properties WHERE id=%s", (pid,))
            remaining = conn.execute(
                "SELECT count(*) FROM comps WHERE id=%s", (cid,)
            ).fetchone()[0]
        assert remaining == 0

    def test_timestamps_are_timezone_aware(self, migrated_db):
        with psycopg.connect(migrated_db) as conn:
            data_type = conn.execute(
                "SELECT data_type FROM information_schema.columns"
                " WHERE table_name='properties' AND column_name='created_at'"
            ).fetchone()[0]
        assert data_type == "timestamp with time zone"

    def test_json_columns_are_json_not_jsonb(self, migrated_db):
        """Documents current reality rather than asserting it is right.

        SQLAlchemy's generic JSON type maps to `json` on PostgreSQL. JSONB
        would be the better choice — it is indexable and faster to query — and
        migration 0003 was written expecting JSONB, but the column already
        existed as `json` so the ADD COLUMN was a no-op. Recorded as known
        technical debt; changing it is a schema migration, not a config tweak.
        """
        with psycopg.connect(migrated_db) as conn:
            types = dict(
                conn.execute(
                    "SELECT column_name, data_type FROM information_schema.columns"
                    " WHERE table_name='user_profiles'"
                    " AND column_name IN ('default_assumptions','investor_profile')"
                ).fetchall()
            )
        assert types == {"default_assumptions": "json", "investor_profile": "json"}
