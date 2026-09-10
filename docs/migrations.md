# Database migrations

Alembic is the authoritative migration runner. It is the only thing that
changes Atlas's schema.

```bash
make db-upgrade     # apply everything this database has not had
make db-current     # where this database is
make db-history     # the whole history
make db-check       # fail if the models have drifted from the migrations
```

Every target reads `ATLAS_DATABASE_URL` through `apps/api/alembic/env.py`, so a
migration cannot be applied to a different database than the one the API talks
to. There is no URL in `alembic.ini` on purpose.

---

## Why this exists

Before Alembic, `database/migrations/` was a directory of `.sql` files applied
by hand. Nothing recorded which database had received which, nothing prevented
applying them out of order, and nothing could roll one back. Two things went
wrong as a direct result:

- **`0001_initial_schema.sql` was regenerated from the models on every schema
  change**, so it always described the *current* schema rather than the one any
  particular database was built from. Migrations `0003` and `0004` were each
  written to add a column that the regenerated `0001` already created, making
  them no-ops on a fresh database. A migration that never migrates anything
  looks exactly like one that works.

- **`init_db()` called `Base.metadata.create_all()`**, which creates missing
  tables and does nothing at all to existing ones. A new column reached fresh
  databases and silently skipped every established one. The e2e suite hit it as
  `no such column: deal_analyses.assumptions_schema_version` raised from inside
  an unrelated query — a long way from the cause.

Both failure modes are now pinned by tests in
`apps/api/tests/test_migrations.py`, including a direct demonstration that
`create_all()` will not add a missing column.

---

## The history

| Revision | What it does |
|---|---|
| `0001_initial_schema` | The twelve tables as originally shipped |
| `0002_row_level_security` | RLS policies — **conditional**, see below |
| `0003_investor_profile` | `user_profiles.investor_profile` |
| `0004_assumptions_schema_version` | `deal_analyses.assumptions_schema_version`, `DEFAULT 0` |

The history is linear: one head, one path. `test_the_history_is_linear` fails if
that stops being true, because a branch makes `upgrade head` ambiguous and lets
two developers' databases diverge while both report success.

`0001` deliberately reconstructs the **original** schema (commit 289b7d2),
without the two columns added later — not the regenerated `.sql` file. That is
what makes `0003` and `0004` real steps and what lets a database sitting at any
point in the history be moved forward.

The pre-Alembic `.sql` files are kept under `database/migrations/legacy/` as a
record and as the reference `scripts/db_baseline.py` recognises. **They are
never applied.**

### `0002` is conditional

The RLS policies call `auth.uid()`, which Supabase provides and PostgreSQL does
not. Running them unconditionally would abort `upgrade head` on every developer
machine and in the whole test suite, and a runner that cannot reach head
locally does not get used.

So the revision applies the policies where `auth.uid()` exists and logs a loud
skip where it does not:

```
WARNI [alembic.runtime.migration] SKIPPING row-level security: auth.uid() is not
available on this database (dialect=postgresql). ... This database has NO
row-level security; the application's owner_id filter is the only protection.
```

That skip is a real gap, not a formality. See
[`database-validation.md`](database-validation.md).

---

## Initializing a new database

Nothing special: point Atlas at an empty database and upgrade.

```bash
export ATLAS_DATABASE_URL=postgresql+psycopg://user:pass@host/atlas
make db-upgrade
```

That creates every table, applies RLS if `auth.uid()` is available, and stamps
the database at head. Verify with:

```bash
make db-current    # -> 0004_assumptions_schema_version (head)
make db-check      # -> No new upgrade operations detected.
```

With no `ATLAS_DATABASE_URL` set, Atlas falls back to SQLite and the same
command builds that file instead. Running the API or `make seed` also upgrades
on startup, so a local database needs no separate step.

---

## Upgrading an existing database

### One already under Alembic

```bash
make db-upgrade
```

Idempotent — a second run is a no-op, which matters because deploy scripts run
it unconditionally.

### One built before Alembic existed

Such a database has the right tables and no record of how it got them, so
Alembic assumes it is empty and tries to create everything again. It must be
**stamped** with the revision it is already at, and guessing that revision is
exactly the mistake a runner exists to prevent. So the script works it out from
the schema:

```bash
make db-baseline              # dry run: says what it would stamp, and why
make db-baseline apply=1      # stamp, then upgrade to head
```

Detection rules:

| Schema | Stamped at |
|---|---|
| No application tables | nothing — it is new, just `make db-upgrade` |
| Tables, no `user_profiles.investor_profile` | `0001_initial_schema` |
| ... plus `investor_profile` | `0003_investor_profile` |
| ... plus `deal_analyses.assumptions_schema_version` | `0004` (head) |

Row-level security is **reported separately, not inferred**, because column
layout cannot reveal it: the hand-applied `0002` was its own file and a project
may or may not have received it. If the script says policies are missing on a
database that has `auth.uid()`, follow the instructions it prints before
stamping — stamping past `0002` would leave that database permanently
unprotected.

The dry run is the default. Read the plan before applying it.

---

## Making a schema change

1. Edit the models in `apps/api/atlas_api/models.py`. They remain the source of
   truth.
2. Generate a revision:
   ```bash
   make db-revision m="add rehab line items"
   ```
3. **Read what it generated.** Autogenerate is a first draft, not an answer. It
   cannot tell a rename from a drop-and-add, it does not know what a new
   `NOT NULL` column should hold on existing rows, and it will not write a data
   migration for you.
4. Apply and verify:
   ```bash
   make db-upgrade
   make db-check     # must report no new operations
   ```
5. Run the tests, including the PostgreSQL ones:
   ```bash
   make test
   make test-postgres
   ```

### Rules for a revision

- **Write a real downgrade.** Not because downgrades get run in anger, but
  because writing one forces you to know what your upgrade actually did.
  `test_every_revision_has_a_downgrade` enforces it.
- **Adding a `NOT NULL` column needs a server default**, or the migration fails
  on any table with rows in it. If the default carries meaning — as
  `assumptions_schema_version` does, where `0` is what preserves the old reading
  of stored zeros — say so in the revision docstring.
- **Both engines.** Atlas runs on PostgreSQL and falls back to SQLite. `env.py`
  turns on batch mode for SQLite so `ALTER TABLE` works there, but engine-
  specific SQL still needs a dialect check — see `0004` for the shape.
- **One head.** Rebase your revision onto the current head rather than creating
  a branch.

---

## Deployment

Run the upgrade as an explicit step, before the new application version starts:

```bash
make db-upgrade && <start the API>
```

`init_db()` also upgrades at startup, and logs a warning when it actually
applies something. That is a safety net for single-process development, not the
deployment mechanism: several replicas starting at once would each try to
migrate, and one would win.

To review the SQL before it touches a database nobody lets CI connect to:

```bash
alembic -c apps/api/alembic.ini upgrade head --sql
```

That prints the statements instead of running them.

---

## Testing

`apps/api/tests/test_migrations.py` covers:

- the history is linear, every revision has a downgrade, no loose `.sql` files
  remain outside `legacy/`
- building from nothing lands exactly on the models (`compare_metadata` is
  empty), is idempotent, and survives a full down-and-up round trip
- each revision does what it claims — `0001` genuinely lacks the two later
  columns, `0003` and `0004` genuinely add them
- **the `create_all()` failure mode**, demonstrated rather than asserted:
  a database at `0003` is unchanged by `create_all()` and fixed by an upgrade
- **an existing PostgreSQL database with data**, stamped and upgraded, with the
  rows intact, the legacy schema version preserved, and the result matching the
  models

The last group needs `ATLAS_TEST_POSTGRES_URL` and runs under
`make test-postgres`.
