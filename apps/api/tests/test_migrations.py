"""The migration path itself.

Two questions this file answers, both of which went unasked until a schema
change broke the e2e suite with `no such column`:

1. Does running the history from nothing produce exactly the schema the models
   describe?
2. Can a database that already exists, with data in it, be moved forward?

The SQLite tests run everywhere and cover the paths a developer actually walks.
The PostgreSQL tests need ATLAS_TEST_POSTGRES_URL and cover the deployed
engine, including the legacy-database upgrade that no other test exercises.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parents[1]
ALEMBIC_INI = API_ROOT / "alembic.ini"

HEAD = "0004_assumptions_schema_version"
EXPECTED_HISTORY = [
    "0001_initial_schema",
    "0002_row_level_security",
    "0003_investor_profile",
    HEAD,
]


def _config(url: str) -> Config:
    import argparse

    config = Config(str(ALEMBIC_INI))
    config.cmd_opts = argparse.Namespace(x=[f"url={url}"])
    return config


def _revision_of(url: str) -> str | None:
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


@pytest.fixture
def sqlite_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path}/migration-test.db"


class TestTheHistoryItself:
    def test_the_history_is_linear(self):
        """One head, one path. A branch means `upgrade head` is ambiguous and
        two developers' databases can diverge while both report success."""
        script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))
        heads = list(script.get_heads())
        assert heads == [HEAD], f"expected a single head, found {heads}"

        walked = [rev.revision for rev in script.walk_revisions()]
        assert list(reversed(walked)) == EXPECTED_HISTORY

    def test_every_revision_has_a_downgrade(self):
        """Not because downgrades get run in anger, but because writing one
        forces you to know what your upgrade actually did."""
        script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))
        for revision in script.walk_revisions():
            source = Path(revision.path).read_text()
            assert "def downgrade()" in source, revision.revision
            body = source.split("def downgrade()", 1)[1]
            assert "pass" not in body.split("\n\n")[0], (
                f"{revision.revision} has an empty downgrade"
            )

    def test_the_legacy_sql_is_not_applied_any_more(self):
        """The pre-Alembic files are kept as a record and as the reference for
        stamping. Two live copies of the schema is the drift this replaced."""
        legacy = REPO_ROOT / "database" / "migrations" / "legacy"
        assert legacy.is_dir()
        assert (legacy / "README.md").exists()
        # Nothing outside that directory should be a loose .sql migration.
        loose = list((REPO_ROOT / "database" / "migrations").glob("*.sql"))
        assert loose == []


class TestBuildingFromNothing:
    def test_upgrade_head_creates_every_table(self, sqlite_url: str):
        command.upgrade(_config(sqlite_url), "head")
        engine = create_engine(sqlite_url)
        try:
            tables = set(inspect(engine).get_table_names())
        finally:
            engine.dispose()
        assert {
            "user_profiles", "properties", "owners", "leads", "deal_analyses",
            "assumption_audit", "comps", "offers", "communications",
            "rehab_projects", "data_sources", "activity_log",
        } <= tables

    def test_the_result_matches_the_models(self, sqlite_url: str):
        """`alembic check` in test form.

        If this fails, someone changed a model without writing a revision — the
        single most common way a migration history stops being authoritative.
        """
        command.upgrade(_config(sqlite_url), "head")
        from alembic.autogenerate import compare_metadata

        from atlas_api.models import Base

        engine = create_engine(sqlite_url)
        try:
            with engine.connect() as connection:
                context = MigrationContext.configure(
                    connection, opts={"compare_type": True}
                )
                diff = compare_metadata(context, Base.metadata)
        finally:
            engine.dispose()
        assert diff == [], f"models and migrations disagree: {diff}"

    def test_the_database_is_stamped_at_head(self, sqlite_url: str):
        command.upgrade(_config(sqlite_url), "head")
        assert _revision_of(sqlite_url) == HEAD

    def test_upgrade_is_idempotent(self, sqlite_url: str):
        """Running it twice must be a no-op, not an error. Deploy scripts run
        it unconditionally, and a second run happens more often than a first."""
        command.upgrade(_config(sqlite_url), "head")
        command.upgrade(_config(sqlite_url), "head")
        assert _revision_of(sqlite_url) == HEAD

    def test_the_full_round_trip(self, sqlite_url: str):
        """Up to head, all the way back down, and up again."""
        config = _config(sqlite_url)
        command.upgrade(config, "head")
        command.downgrade(config, "base")
        assert _revision_of(sqlite_url) is None

        engine = create_engine(sqlite_url)
        try:
            remaining = set(inspect(engine).get_table_names()) - {"alembic_version"}
        finally:
            engine.dispose()
        assert remaining == set(), f"downgrade left tables behind: {remaining}"

        command.upgrade(config, "head")
        assert _revision_of(sqlite_url) == HEAD


class TestStepByStep:
    """Each revision must do what it says, not merely end up in the right place.

    Under the old scheme 0003 and 0004 were both no-ops — the regenerated
    0001.sql already contained the columns they claimed to add — and nothing
    noticed for months. These tests are the thing that would have noticed.
    """

    def test_the_initial_revision_omits_the_later_columns(self, sqlite_url: str):
        command.upgrade(_config(sqlite_url), "0001_initial_schema")
        engine = create_engine(sqlite_url)
        try:
            inspector = inspect(engine)
            user_columns = {c["name"] for c in inspector.get_columns("user_profiles")}
            analysis_columns = {
                c["name"] for c in inspector.get_columns("deal_analyses")
            }
        finally:
            engine.dispose()
        assert "investor_profile" not in user_columns
        assert "assumptions_schema_version" not in analysis_columns

    def test_0003_adds_the_investor_profile_column(self, sqlite_url: str):
        config = _config(sqlite_url)
        command.upgrade(config, "0001_initial_schema")
        command.upgrade(config, "0003_investor_profile")
        engine = create_engine(sqlite_url)
        try:
            columns = {c["name"] for c in inspect(engine).get_columns("user_profiles")}
        finally:
            engine.dispose()
        assert "investor_profile" in columns

    def test_0004_adds_the_schema_version_column_defaulting_to_legacy(
        self, sqlite_url: str
    ):
        """The default of 0 is the mechanism, not a detail.

        A row that predates the tri-state change must read back as version 0 so
        its stored zeros keep meaning "unfilled". Defaulting to the current
        version would silently reinterpret every historical analysis.
        """
        config = _config(sqlite_url)
        command.upgrade(config, "0003_investor_profile")

        engine = create_engine(sqlite_url)
        pid, aid = str(uuid.uuid4()), str(uuid.uuid4())
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO properties (id, owner_id, address,"
                        " property_status, created_at, updated_at) VALUES"
                        " (:pid, :owner, '1 Pre-Migration Way', 'prospect',"
                        " CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    ),
                    {"pid": pid, "owner": str(uuid.uuid4())},
                )
                connection.execute(
                    text(
                        "INSERT INTO deal_analyses (id, property_id, owner_id,"
                        " requires_human_review, created_at, updated_at) VALUES"
                        " (:aid, :pid, :owner, 0, CURRENT_TIMESTAMP,"
                        " CURRENT_TIMESTAMP)"
                    ),
                    {"aid": aid, "pid": pid, "owner": str(uuid.uuid4())},
                )
        finally:
            engine.dispose()

        command.upgrade(config, "head")

        engine = create_engine(sqlite_url)
        try:
            with engine.connect() as connection:
                version = connection.execute(
                    text(
                        "SELECT assumptions_schema_version FROM deal_analyses"
                        " WHERE id = :aid"
                    ),
                    {"aid": aid},
                ).scalar()
        finally:
            engine.dispose()
        assert version == 0, "a pre-existing analysis was not marked as legacy"


class TestTheCreateAllFailureMode:
    """The bug that made a migration runner non-optional.

    `Base.metadata.create_all()` creates tables that do not exist and does
    nothing whatsoever to tables that do. A column added to a model therefore
    reached fresh databases and silently skipped every established one. The
    e2e suite hit it as `no such column: deal_analyses.assumptions_schema_version`
    from inside an unrelated query, hours of confusion away from the cause.
    """

    def _database_at_0003(self, url: str) -> None:
        command.upgrade(_config(url), "0003_investor_profile")

    def test_create_all_does_not_add_a_missing_column(self, sqlite_url: str):
        """The failure, reproduced. Not a hypothesis — a demonstration."""
        self._database_at_0003(sqlite_url)

        from atlas_api.models import Base

        engine = create_engine(sqlite_url)
        try:
            # The models declare assumptions_schema_version. create_all sees the
            # table already exists and returns happily, having done nothing.
            Base.metadata.create_all(bind=engine)
            columns = {c["name"] for c in inspect(engine).get_columns("deal_analyses")}
        finally:
            engine.dispose()

        assert "assumptions_schema_version" not in columns, (
            "create_all altered an existing table — if this ever becomes true, "
            "this test and the reasoning in db.init_db need revisiting"
        )

    def test_the_migration_does_add_it(self, sqlite_url: str):
        """The same starting point, through the runner instead."""
        self._database_at_0003(sqlite_url)
        command.upgrade(_config(sqlite_url), "head")

        engine = create_engine(sqlite_url)
        try:
            columns = {c["name"] for c in inspect(engine).get_columns("deal_analyses")}
        finally:
            engine.dispose()
        assert "assumptions_schema_version" in columns

    def test_init_db_upgrades_an_existing_database(self, sqlite_url: str, monkeypatch):
        """init_db() is the path the API takes at startup, so it is the path
        that has to be right.

        Both the engine and the settings URL are redirected: init_db reads the
        current revision through the engine and applies migrations through the
        URL, and pointing only one of them at the test database would quietly
        migrate the wrong one.
        """
        self._database_at_0003(sqlite_url)

        import atlas_api.db as db

        engine = create_engine(sqlite_url)
        monkeypatch.setattr(db, "engine", engine)
        monkeypatch.setattr(db._settings, "atlas_database_url", sqlite_url)
        try:
            db.init_db()
            columns = {c["name"] for c in inspect(engine).get_columns("deal_analyses")}
        finally:
            engine.dispose()
        assert "assumptions_schema_version" in columns


# --------------------------------------------------------------------------
# Existing databases
# --------------------------------------------------------------------------
#
# These need a real PostgreSQL server because that is what a deployed Atlas
# runs on, and the whole question is what happens to a database that already
# exists. They skip without ATLAS_TEST_POSTGRES_URL.

pg = pytest.importorskip("psycopg")

from pg_support import (  # noqa: E402
    POSTGRES_URL,
    alembic_config,
    as_sqlalchemy_url,
    server_reachable,
    throwaway_database,
)

postgres_only = pytest.mark.skipif(
    not POSTGRES_URL, reason="ATLAS_TEST_POSTGRES_URL is not set"
)


def _unstamped_database_at(url: str, revision: str) -> None:
    """Simulate a hand-applied database: the right schema, no bookkeeping.

    Built by running the history to `revision` and then deleting Alembic's
    version table — which leaves precisely what the pre-Alembic SQL files
    produced, and is what `scripts/db_baseline.py` has to recognise.
    """
    command.upgrade(alembic_config(url), revision)
    with pg.connect(url, autocommit=True) as conn:
        conn.execute("DROP TABLE alembic_version")


def _seed_legacy_rows(url: str) -> tuple[str, str]:
    property_id, analysis_id = str(uuid.uuid4()), str(uuid.uuid4())
    owner = str(uuid.uuid4())
    with pg.connect(url, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO properties (id, owner_id, address, property_status,"
            " created_at, updated_at)"
            " VALUES (%s,%s,'9 Legacy Lane','prospect',now(),now())",
            (property_id, owner),
        )
        conn.execute(
            "INSERT INTO deal_analyses (id, property_id, owner_id,"
            " requires_human_review, purchase_price, created_at, updated_at)"
            " VALUES (%s,%s,%s,false,150000.00,now(),now())",
            (analysis_id, property_id, owner),
        )
    return property_id, analysis_id


@postgres_only
class TestExistingDatabaseUpgrade:
    """The path a deployed database actually takes.

    Nothing else in the suite covers it: every other test starts from nothing.
    An upgrade that works on an empty database and corrupts a full one is the
    exact failure a migration runner is supposed to prevent.
    """

    def test_baseline_detects_the_revision_of_an_unstamped_database(self):
        if not server_reachable():
            pytest.skip("PostgreSQL is not reachable")
        import sys

        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from db_baseline import detect_revision

        with throwaway_database("atlas_legacy") as url:
            _unstamped_database_at(url, "0001_initial_schema")
            engine = create_engine(as_sqlalchemy_url(url))
            try:
                assert detect_revision(inspect(engine)) == "0001_initial_schema"
            finally:
                engine.dispose()

    def test_baseline_detects_head_on_a_fully_migrated_database(self):
        """A database built from the regenerated legacy SQL already had every
        column, so it must be stamped at head, not replayed from 0001."""
        if not server_reachable():
            pytest.skip("PostgreSQL is not reachable")
        import sys

        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from db_baseline import detect_revision

        with throwaway_database("atlas_legacy") as url:
            _unstamped_database_at(url, "head")
            engine = create_engine(as_sqlalchemy_url(url))
            try:
                assert detect_revision(inspect(engine)) == HEAD
            finally:
                engine.dispose()

    def test_baseline_reports_an_empty_database_as_nothing_to_stamp(self):
        if not server_reachable():
            pytest.skip("PostgreSQL is not reachable")
        import sys

        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from db_baseline import detect_revision

        with throwaway_database("atlas_empty") as url:
            engine = create_engine(as_sqlalchemy_url(url))
            try:
                assert detect_revision(inspect(engine)) is None
            finally:
                engine.dispose()

    def test_a_legacy_database_upgrades_without_losing_data(self):
        """Stamp, upgrade, and check the rows are still there and unchanged."""
        if not server_reachable():
            pytest.skip("PostgreSQL is not reachable")

        with throwaway_database("atlas_legacy") as url:
            _unstamped_database_at(url, "0001_initial_schema")
            property_id, analysis_id = _seed_legacy_rows(url)

            config = alembic_config(url)
            command.stamp(config, "0001_initial_schema")
            command.upgrade(config, "head")

            with pg.connect(url) as conn:
                address = conn.execute(
                    "SELECT address FROM properties WHERE id = %s", (property_id,)
                ).fetchone()[0]
                price, version = conn.execute(
                    "SELECT purchase_price, assumptions_schema_version"
                    " FROM deal_analyses WHERE id = %s",
                    (analysis_id,),
                ).fetchone()
                stamped = conn.execute(
                    "SELECT version_num FROM alembic_version"
                ).fetchone()[0]

        assert address == "9 Legacy Lane"
        assert str(price) == "150000.00"
        assert stamped == HEAD
        # The row predates the tri-state change, so it must read as legacy.
        assert version == 0

    def test_upgrading_a_legacy_database_lands_on_the_models(self):
        """Same destination as a database built from nothing. If these two
        diverge, half the fleet is running a schema nobody described."""
        if not server_reachable():
            pytest.skip("PostgreSQL is not reachable")
        from alembic.autogenerate import compare_metadata

        from atlas_api.models import Base

        with throwaway_database("atlas_legacy") as url:
            _unstamped_database_at(url, "0001_initial_schema")
            _seed_legacy_rows(url)
            config = alembic_config(url)
            command.stamp(config, "0001_initial_schema")
            command.upgrade(config, "head")

            engine = create_engine(as_sqlalchemy_url(url))
            try:
                with engine.connect() as connection:
                    context = MigrationContext.configure(
                        connection, opts={"compare_type": True}
                    )
                    diff = compare_metadata(context, Base.metadata)
            finally:
                engine.dispose()
        assert diff == [], f"legacy upgrade did not reach the models: {diff}"

    def test_create_all_on_a_legacy_database_leaves_it_broken(self):
        """The old behaviour, on the engine that matters.

        create_all() reports success and the missing column is still missing —
        so the application starts, and fails on the first query that touches it.
        """
        if not server_reachable():
            pytest.skip("PostgreSQL is not reachable")
        from atlas_api.models import Base

        with throwaway_database("atlas_legacy") as url:
            _unstamped_database_at(url, "0001_initial_schema")
            engine = create_engine(as_sqlalchemy_url(url))
            try:
                Base.metadata.create_all(bind=engine)
                columns = {
                    c["name"] for c in inspect(engine).get_columns("deal_analyses")
                }
            finally:
                engine.dispose()
            assert "assumptions_schema_version" not in columns

            with pg.connect(url) as conn:
                with pytest.raises(pg.errors.UndefinedColumn):
                    conn.execute(
                        "SELECT assumptions_schema_version FROM deal_analyses"
                    )
