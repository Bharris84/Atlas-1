# Database and RLS validation

Until this point Atlas's PostgreSQL schema and its row-level security policies
had never been executed. The test suite ran on SQLite, and `0002_row_level_security.sql`
had never been applied to any database at all. "The schema works" and "RLS is
implemented" were both claims about files, not about behaviour.

This document records what was actually run, what it proved, and what it did
not. Everything here is reproducible:

```bash
make test-postgres
```

The target needs a reachable server and a role that may `CREATE DATABASE` and
`CREATE ROLE`; each test module builds a throwaway database and drops it again.
Without `ATLAS_TEST_POSTGRES_URL` — or without `psycopg` installed — both
modules skip, so `make test` still runs anywhere.

Validated against **PostgreSQL 16.13** on 2026-09-10.

---

## 1. The schema (`apps/api/tests/test_postgres_schema.py`, 7 tests)

| Check | Result |
|---|---|
| `0001_initial_schema.sql` applies to an empty database | Clean, no errors |
| All 12 tables are created | Confirmed |
| `0003_investor_profile.sql` is re-runnable | Confirmed idempotent |
| Migration SQL vs. `Base.metadata.create_all()` | **Byte-identical column sets** |
| `NUMERIC(14,2)` money columns | `123456.789` stores as `123456.79`, as `Decimal` |
| `ON DELETE CASCADE` | Deleting a property removes its comps |
| Timestamps | `timestamp with time zone` |

Two of these deserve a note.

**The migration and the ORM agree — but nothing was enforcing it.** The SQL is
generated from the models by `scripts/generate_migration.py`, so drift was
always possible and would have been silent. The comparison is now a test.

**`0003` is a no-op.** It adds `investor_profile` to `user_profiles`, but the
regenerated `0001` already contains that column, so `ADD COLUMN IF NOT EXISTS`
finds nothing to do. This is harmless on a fresh database and correct on an
existing one; it is only confusing to read. Left as-is.

---

## 2. Row-level security (`apps/api/tests/test_rls.py`, 18 tests)

### The honest framing

`0002_row_level_security.sql` calls `auth.uid()`. That function is **provided
by Supabase, not by PostgreSQL**. Applied to a vanilla PostgreSQL 16 database,
the migration fails outright:

```
ERROR:  schema "auth" does not exist
```

That failure is itself now a test (`test_the_migration_needs_supabase_and_says_so`),
because it is the single most important fact about Atlas's RLS: **it is
Supabase-specific**. Point Atlas at a plain PostgreSQL database and there is no
row-level security at all — only the application-level `owner_id` filter.

To test the policies anyway, `apps/api/tests/sql/supabase_auth_shim.sql`
recreates `auth.uid()` from `request.jwt.claims`, the same per-connection
setting Supabase populates from a verified JWT. The shim lives under `tests/`
and deliberately **not** under `database/migrations/`, so it can never reach a
production database.

What that arrangement proves and does not prove:

| | |
|---|---|
| **Proves** | The policy SQL is valid, attaches to the intended tables, and its `USING` / `WITH CHECK` predicates isolate rows by owner. |
| **Does not prove** | Supabase's own auth behaviour: that a JWT is verified correctly, that the claim reaches the right connection, or that Supabase's role grants match these. Only a real Supabase project can confirm that. |

Anything stronger would be pretending vanilla PostgreSQL validates Supabase.

### What passed

All 12 protected tables have RLS enabled and all 13 policies install.

**Ownership isolation** — user A and user B, each connecting as a non-owning
role with their own claim:

- A sees only A's properties; B sees only B's.
- Knowing another user's primary key grants nothing: the row is not found.
- `UPDATE` and `DELETE` against another user's row affect 0 rows, and the row
  is verifiably unchanged afterwards.
- Inserting a row owned by someone else is rejected (`WITH CHECK`, not merely
  `USING` — without it a user could write into another account while unable to
  read it back).
- Reassigning your own row to another account is rejected.

**Inherited ownership** — `owners`, `comps` and `data_sources` have no
`owner_id`; they inherit through `property_id` via an `EXISTS` subquery. That
join is easy to get subtly wrong, so it is tested directly: child rows follow
their property, and a child cannot be attached to another user's property. The
deliberate exception is pinned too — `data_sources` with `property_id IS NULL`
are market-wide records visible to everyone.

**Audit-trail immutability** — `assumption_audit` grants `SELECT` and `INSERT`
only. There is no `UPDATE` or `DELETE` policy, and a table with RLS enabled
denies whatever no policy permits, so the *absence* of a policy is the
enforcement. Confirmed: the owner can read their trail, nobody can rewrite or
delete an entry, and an entry cannot be attributed to another user
(`changed_by = auth.uid()`).

**Failing closed** — a connection with no claim makes `auth.uid()` NULL, every
predicate compares against NULL, and the user sees nothing. The dangerous
failure mode would be the opposite.

### The finding: the table owner bypasses RLS entirely

PostgreSQL exempts a table's owner from that table's own policies unless the
table is set to `FORCE ROW LEVEL SECURITY`. Atlas does not set it. Connected as
the role that created the tables — while claiming, via the JWT setting, to be a
*different* user — every row is still visible.

This is correct for the deployment Atlas targets and wrong for another:

- **Under Supabase**, end users arrive through PostgREST as the `authenticated`
  role, which does not own the tables. The policies apply. The API's own
  service connection is *supposed* to see everything; it scopes by `owner_id`
  in application code.
- **Against plain PostgreSQL**, using the role that created the tables, RLS
  contributes nothing whatsoever.

`FORCE ROW LEVEL SECURITY` is not a one-line fix: Atlas's API connects through
SQLAlchemy and never sets `request.jwt.claims`, so forcing RLS would make the
API see zero rows. It is a deployment decision, not a tidy-up. Recorded as a
test (`test_the_table_owner_bypasses_rls_entirely`) so it cannot quietly stop
being true in either direction.

---

## 3. Technical debt found

### No versioned migration runner

`database/migrations/` is a directory of `.sql` files applied by hand. Nothing
records which migrations a given database has received, nothing prevents
applying them out of order, and nothing can roll one back. `0003` being a
silent no-op is a symptom: with a runner, the fact that it changed nothing
would have been visible.

Adopting Alembic was considered during this Reality Check and **deliberately
deferred by the product owner**. It is recorded here as known debt, to be taken
on before the schema starts changing under real data.

### JSON columns are `json`, not `jsonb`

Both `user_profiles.default_assumptions` and `user_profiles.investor_profile`
— and the five `*_json` columns on `deal_analyses` — are PostgreSQL `json`.
SQLAlchemy's generic `JSON` type maps to `json` on PostgreSQL, and migration
0003 was written expecting `jsonb` but its `ADD COLUMN` was a no-op, so the
mismatch never surfaced.

`jsonb` would be the better choice: it is indexable, faster to query, and
normalises whitespace and key order. `json` preserves the exact text, which
Atlas does not need. Changing it is a schema migration over existing rows, not
a config tweak, so it waits for a migration runner. Pinned by
`test_json_columns_are_json_not_jsonb`, which documents current reality rather
than asserting it is right.

### RLS is unverifiable outside Supabase

Covered above. The gap that remains after these tests is Supabase's own auth
layer, and closing it requires running against a real Supabase project.

---

## 4. What is still not validated

- Supabase JWT verification end to end, against a live project.
- Behaviour under concurrent writes; there is no load or contention testing.
- Index effectiveness — the indexes exist, but no query plan has been examined
  against a realistic row count.
- Migration *sequencing* on a database that already holds data, which is the
  thing a migration runner would give.
