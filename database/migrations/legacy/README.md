# Pre-Alembic migrations — historical record, never applied

**Do not run these files.** They are kept because deployed databases were built
from them, and `scripts/db_baseline.py` decides which Alembic revision to stamp
by recognising the schema they produce. Delete them and that recognition loses
its reference.

The authoritative migrations now live in `apps/api/alembic/versions/`.

## What was wrong with this scheme

These four files were applied by hand, in whatever order someone chose, with no
record of which database had received which. That is the debt the Reality Check
recorded and Alembic cleared. Two concrete symptoms:

- **`0001_initial_schema.sql` was regenerated from the models on every schema
  change.** So the file always described the *current* schema, never the one any
  particular database was built from. `0003` and `0004` were consequently no-ops
  against it on a fresh database — each was written to add a column that the
  regenerated `0001` already created. A migration that never migrates anything
  looks exactly like one that works.

- **Nothing altered an existing table.** `init_db()` used
  `Base.metadata.create_all()`, which creates missing tables and ignores
  existing ones. A new column reached fresh databases and silently skipped
  every established one, surfacing later as `no such column` from inside an
  unrelated query.

## How the history maps onto Alembic

| This file | Alembic revision | Note |
|---|---|---|
| `0001_initial_schema.sql` | `0001_initial_schema` | The Alembic revision reconstructs the **original** 0001 (commit 289b7d2), without the two columns added later — not this regenerated file |
| `0002_row_level_security.sql` | `0002_row_level_security` | SQL carried over verbatim, plus `DROP POLICY IF EXISTS` so it is re-runnable, and a guard that skips where `auth.uid()` is absent |
| `0003_investor_profile.sql` | `0003_investor_profile` | A real step now: revision 0001 does not create the column |
| `0004_assumptions_schema_version.sql` | `0004_assumptions_schema_version` | Same column, same `DEFAULT 0`, which is what preserves legacy assumption semantics |

See [`docs/migrations.md`](../../../docs/migrations.md) for the workflow.
