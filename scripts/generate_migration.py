"""Regenerate the base SQL schema from the SQLAlchemy models.

The models in ``apps/api/atlas_api/models.py`` are the source of truth. This
emits the equivalent PostgreSQL DDL so the migration file and the ORM cannot
drift apart.

    python scripts/generate_migration.py

Only the initial schema is generated. Subsequent changes are hand-written
migrations, because a generator cannot know whether a renamed column is a
rename or a drop-and-add — and getting that wrong loses data.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from sqlalchemy.dialects import postgresql  # noqa: E402
from sqlalchemy.schema import CreateIndex, CreateTable  # noqa: E402

from atlas_api.models import Base  # noqa: E402

HEADER = """-- Atlas initial schema (PostgreSQL / Supabase)
--
-- Generated from the SQLAlchemy models in apps/api/atlas_api/models.py, which
-- remain the source of truth. Regenerate with `make migration`.
--
-- Conventions:
--   * Money is NUMERIC(14,2) and rates are NUMERIC(12,6). No floats, ever.
--   * NULL means unknown. It never means zero.
--   * owner_id is the Supabase Auth user id (auth.users.id).

BEGIN;

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
"""


def generate() -> str:
    dialect = postgresql.dialect()
    statements = []
    for table in Base.metadata.sorted_tables:
        statements.append(str(CreateTable(table).compile(dialect=dialect)).strip() + ";")
        # table.indexes is a set: without sorting, regenerating shuffles the
        # CREATE INDEX lines and every `make migration` produces a diff that
        # says nothing.
        for index in sorted(table.indexes, key=lambda i: i.name or ""):
            statements.append(str(CreateIndex(index).compile(dialect=dialect)).strip() + ";")
    return HEADER + "\n" + "\n\n".join(statements) + "\n\nCOMMIT;\n"


if __name__ == "__main__":
    target = ROOT / "database" / "migrations" / "0001_initial_schema.sql"
    target.write_text(generate())
    print(f"wrote {target.relative_to(ROOT)}")
