"""Schema validation against a real PostgreSQL server.

The rest of the suite runs on SQLite, which is fine for behaviour but proves
nothing about the production engine: JSON handling, NUMERIC precision, cascade
deletes and timezone semantics all differ. These tests close that gap.

The database under test is built by running the Alembic history from nothing,
so a broken revision fails here rather than in production.

Skipped automatically when no PostgreSQL is reachable, so the default suite
still runs anywhere. Point ATLAS_TEST_POSTGRES_URL at a server to enable them:

    ATLAS_TEST_POSTGRES_URL=postgresql://atlas:atlas@127.0.0.1:5432/postgres \
        pytest tests/test_postgres_schema.py
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

psycopg = pytest.importorskip("psycopg")

from pg_support import (  # noqa: E402
    POSTGRES_URL,
    alembic_config,
    as_sqlalchemy_url,
    server_reachable,
    throwaway_database,
)

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL, reason="ATLAS_TEST_POSTGRES_URL is not set"
)

# Alembic's own bookkeeping table. It is part of the database, not part of
# Atlas's schema, so every comparison against the models excludes it.
ALEMBIC_TABLE = "alembic_version"


@pytest.fixture(scope="module")
def migrated_db():
    """A database built by running the Alembic history from nothing."""
    if not server_reachable():
        pytest.skip("PostgreSQL is not reachable")
    from alembic import command

    with throwaway_database("atlas_mig") as url:
        command.upgrade(alembic_config(url), "head")
        yield url


@pytest.fixture(scope="module")
def orm_db():
    """A database built by SQLAlchemy's create_all().

    Kept as the comparison target for the drift test below. It is NOT how any
    Atlas database is built any more — see test_migrations.py for why.
    """
    if not server_reachable():
        pytest.skip("PostgreSQL is not reachable")
    with throwaway_database("atlas_orm") as url:
        from sqlalchemy import create_engine

        from atlas_api.models import Base

        engine = create_engine(as_sqlalchemy_url(url))
        Base.metadata.create_all(bind=engine)
        engine.dispose()
        yield url


def _columns(url: str):
    with psycopg.connect(url) as conn:
        return conn.execute(
            """
            SELECT table_name, column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name <> %s
            ORDER BY table_name, column_name
            """,
            (ALEMBIC_TABLE,),
        ).fetchall()


class TestMigrationApplies:
    def test_the_initial_migration_creates_every_table(self, migrated_db):
        with psycopg.connect(migrated_db) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public'"
                ).fetchall()
            } - {ALEMBIC_TABLE}
        assert tables == {
            "user_profiles", "properties", "owners", "leads", "deal_analyses",
            "assumption_audit", "comps", "offers", "communications",
            "rehab_projects", "data_sources", "activity_log",
        }

    def test_the_database_is_stamped_at_head(self, migrated_db):
        """The point of a runner: the database records where it is.

        Without this row, Alembic treats the database as empty and the next
        upgrade tries to create tables that already exist.
        """
        with psycopg.connect(migrated_db) as conn:
            version = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        assert version == ("0004_assumptions_schema_version",)

    def test_an_existing_analysis_defaults_to_the_legacy_schema_version(
        self, migrated_db
    ):
        """The whole point of the column: rows written before the tri-state
        change must read back as legacy, so their stored zeros are understood
        as "unfilled" rather than as a property with no tax bill."""
        with psycopg.connect(migrated_db, autocommit=True) as conn:
            pid, aid = uuid.uuid4(), uuid.uuid4()
            conn.execute(
                "INSERT INTO properties (id, owner_id, address, property_status,"
                " created_at, updated_at) VALUES (%s,%s,'4 Test St','prospect',"
                "now(),now())",
                (pid, uuid.uuid4()),
            )
            # Written the way a pre-0004 INSERT would have been: no mention of
            # the new column at all.
            conn.execute(
                "INSERT INTO deal_analyses (id, property_id, owner_id,"
                " requires_human_review, created_at, updated_at)"
                " VALUES (%s,%s,%s,false,now(),now())",
                (aid, pid, uuid.uuid4()),
            )
            version = conn.execute(
                "SELECT assumptions_schema_version FROM deal_analyses WHERE id=%s",
                (aid,),
            ).fetchone()[0]
        assert version == 0


class TestMigrationMatchesTheOrm:
    def test_no_drift_between_the_migrations_and_the_models(
        self, migrated_db, orm_db
    ):
        """Running the history must land exactly where the models say.

        `alembic check` asserts the same thing from Alembic's own comparison;
        this asserts it from the database's, which is the one that matters when
        a revision does something autogenerate would not have produced.
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
        the legacy 0003 SQL was written expecting JSONB, but the column already
        existed as `json` so the ADD COLUMN was a no-op. Recorded as known
        technical debt; changing it is a schema migration, not a config tweak —
        and now that a runner exists, one that can actually be written.
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
