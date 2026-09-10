"""Bring a pre-Alembic database under Alembic's control.

Atlas's schema was applied by hand from ``database/migrations/*.sql`` before
Alembic existed. Such a database has the right tables and no record of how it
got them, so Alembic assumes it is empty and tries to create everything again.

The fix is to *stamp* it: write the revision it is already at into
``alembic_version`` without running anything. The only hard part is knowing
which revision that is, and an operator guessing is exactly the failure this
whole change is meant to remove. So this script works it out by looking at the
schema:

    no alembic_version, no tables      -> nothing to stamp; run an upgrade
    tables, no investor_profile        -> 0001_initial_schema
    + investor_profile                 -> 0003_investor_profile
    + assumptions_schema_version       -> 0004_assumptions_schema_version (head)

Row-level security is reported separately rather than inferred, because it is
the one step whose presence the column layout cannot reveal.

    python scripts/db_baseline.py              # dry run: say what it would do
    python scripts/db_baseline.py --apply      # write the stamp
    python scripts/db_baseline.py --apply --upgrade   # stamp, then upgrade

Nothing here writes to an application table, and the dry run is the default:
stamping the wrong revision skips a real migration, so it is worth reading the
plan before running it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, inspect, text  # noqa: E402

from atlas_api.config import get_settings  # noqa: E402

ALEMBIC_INI = ROOT / "apps" / "api" / "alembic.ini"
HEAD = "0004_assumptions_schema_version"

# Every table the initial revision creates. Their presence is what makes a
# database "existing" rather than "empty".
APPLICATION_TABLES = {
    "user_profiles", "properties", "owners", "leads", "deal_analyses",
    "assumption_audit", "comps", "offers", "communications", "rehab_projects",
    "data_sources", "activity_log",
}


def _alembic_config(url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    # env.py resolves the URL from Atlas settings; passing it as an -x argument
    # keeps this script and a manual `alembic -x url=...` on the same path.
    config.cmd_opts = argparse.Namespace(x=[f"url={url}"])
    return config


def _columns(inspector, table: str) -> set:
    if table not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def detect_revision(inspector) -> str | None:
    """The revision this database is already at, or None if it is empty."""
    tables = set(inspector.get_table_names())
    if not (tables & APPLICATION_TABLES):
        return None
    if "assumptions_schema_version" in _columns(inspector, "deal_analyses"):
        return HEAD
    if "investor_profile" in _columns(inspector, "user_profiles"):
        return "0003_investor_profile"
    return "0001_initial_schema"


def describe_rls(connection) -> str:
    """Report row-level security rather than inferring it from columns.

    A database can hold every column and no policies — the hand-applied 0002
    was a separate file that a Supabase project may or may not have received.
    """
    if connection.dialect.name != "postgresql":
        return "not applicable on this engine (row-level security is PostgreSQL only)"
    has_auth = connection.execute(
        text(
            "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace"
            " WHERE n.nspname = 'auth' AND p.proname = 'uid'"
        )
    ).scalar()
    policies = connection.execute(
        text("SELECT count(*) FROM pg_policies WHERE schemaname = 'public'")
    ).scalar()
    if not has_auth:
        return (
            f"{policies} policies; auth.uid() is ABSENT, so revision 0002 will "
            "skip and this database has no row-level security"
        )
    if policies == 0:
        return (
            "auth.uid() is available but NO policies are present — revision 0002 "
            "was never applied here. Stamping past it would leave this database "
            "permanently unprotected. Apply the policies before stamping:\n"
            "        alembic -c apps/api/alembic.ini downgrade 0001_initial_schema\n"
            "        alembic -c apps/api/alembic.ini upgrade head"
        )
    return f"{policies} policies applied, auth.uid() available"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the stamp")
    parser.add_argument(
        "--upgrade", action="store_true", help="run `upgrade head` after stamping"
    )
    parser.add_argument("--url", help="override ATLAS_DATABASE_URL")
    args = parser.parse_args()

    url = args.url or get_settings().atlas_database_url
    engine = create_engine(url)

    with engine.connect() as connection:
        inspector = inspect(connection)
        already_managed = "alembic_version" in inspector.get_table_names()
        stamped = None
        if already_managed:
            stamped = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar()
        detected = detect_revision(inspector)
        rls = describe_rls(connection)

    print(f"database         : {url.split('@')[-1]}")
    print(f"row-level security: {rls}")

    if already_managed:
        print(f"alembic_version  : {stamped}")
        print("\nAlready under Alembic. Nothing to baseline.")
        print("Run `make db-upgrade` to move it to head.")
        engine.dispose()
        return 0

    if detected is None:
        print("alembic_version  : absent")
        print("schema           : empty")
        print(
            "\nNothing to baseline — this is a new database. Run `make db-upgrade`,\n"
            "which will create the schema from the migration history."
        )
        engine.dispose()
        return 0

    print("alembic_version  : absent")
    print(f"detected revision: {detected}")

    if not args.apply:
        print(
            f"\nDRY RUN. Would stamp this database at {detected} without running any\n"
            "migration. Re-run with --apply to write it, and add --upgrade to move\n"
            "to head afterwards."
        )
        engine.dispose()
        return 0

    config = _alembic_config(url)
    command.stamp(config, detected)
    print(f"\nStamped at {detected}.")

    if args.upgrade:
        command.upgrade(config, "head")
        print("Upgraded to head.")
    elif detected != HEAD:
        print("Run `make db-upgrade` to apply the remaining revisions.")

    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
