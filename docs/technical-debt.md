# Technical debt

Everything known to be wrong, incomplete, or deferred, with why it was left and
what it would take to clear. Kept in one place so nobody has to rediscover it,
and so a decision to defer stays a decision rather than becoming an oversight.

Nothing here is a bug in the sense of "produces a wrong number". Items that
would produce a wrong number get fixed, not listed.

Last reviewed: 2026-09-10, at the end of the Reality Check phase.

---

## Database

### 1. No versioned migration runner — **highest priority**

`database/migrations/` is a directory of `.sql` files applied by hand. Nothing
records which migrations a database has received, nothing prevents applying
them out of order, and nothing rolls one back.

The symptoms are already visible:

- `0003_investor_profile.sql` is a silent no-op — the regenerated `0001`
  already contains the column it adds. With a runner, "this migration changed
  nothing" would have been an observable fact rather than a discovery.
- The e2e suite had to start deleting its SQLite file, because `create_all()`
  adds tables but never alters an existing one, so a schema change plus a
  leftover database failed deep inside a query with `no such column`.

**Why deferred:** product-owner decision during the Reality Check. Adopting
Alembic mid-phase would have expanded the work beyond what was approved.

**To clear:** adopt Alembic, stamp existing databases at 0004, and generate
subsequent revisions from the models. Do it **before the schema changes again
under real data** — retrofitting a runner over an unknown deployed state is
much worse than adopting one now.

### 2. JSON columns are `json`, not `jsonb`

`user_profiles.default_assumptions`, `user_profiles.investor_profile` and the
five `*_json` columns on `deal_analyses`. SQLAlchemy's generic `JSON` type maps
to `json` on PostgreSQL; `jsonb` is indexable, faster to query, and normalises
whitespace and key order. Atlas does not need `json`'s exact-text preservation.

Pinned by `test_json_columns_are_json_not_jsonb`, which documents reality
rather than asserting it is right.

**To clear:** a type-changing migration over existing rows — so it waits on
item 1.

### 3. RLS is Supabase-specific and unverifiable outside it

`0002_row_level_security.sql` calls `auth.uid()`, which Supabase provides and
PostgreSQL does not. Applied to a vanilla server it fails outright. Atlas
pointed at plain PostgreSQL has **no row-level security at all** — only the
application's own `owner_id` filter.

The policies themselves are tested (18 tests, via a test-only `auth.uid()`
shim). What remains unverified is Supabase's own auth: JWT verification, how
the claim reaches the connection, and Supabase's role grants.

**To clear:** run the RLS suite against a real Supabase project.

### 4. The table owner bypasses RLS

PostgreSQL exempts a table's owner from its own policies unless the table is
set to `FORCE ROW LEVEL SECURITY`, and Atlas does not set it.

This is correct for Supabase — end users arrive as `authenticated`, which does
not own the tables — and wrong for a plain-PostgreSQL deployment connecting as
the role that created them.

**Why not simply fix it:** Atlas's API connects through SQLAlchemy and never
sets `request.jwt.claims`, so forcing RLS would make the API see zero rows. It
is a deployment decision, not a one-line change. Pinned as a test so it cannot
change unnoticed.

See [`database-validation.md`](database-validation.md) for the full record.

---

## Modelling

### 5. Every financial assumption is still provisional

The defaults in `docs/financial-model.md` are starting points chosen so the
engine returns an answer, not figures derived from data. Vacancy at 5%,
maintenance at 5%, the 15% rehab contingency, the 2% buffers — none has been
checked against a real outcome.

**Why deferred:** product-owner decision, and the right one. Replacing one
guess with another guess is not progress.

**To clear:** run real deals through `scripts/calibrate.py`. Three deals will
show a large systematic bias and nothing finer; the report says so itself.
Until then, treat every default as an input to be overridden, not a finding.

### 6. Only taxes and insurance block on being unknown

HOA and utilities are reported as unknown but do not force human review,
because most properties have no association and many rentals are
tenant-metered. That is a judgement about typical properties, not a
verified frequency. If real usage shows unknown HOA dues materially changing
verdicts, the list in `BLOCKING_UNKNOWN_EXPENSES` should grow.

---

## Cross-language duplication

### 7. `ASSUMPTIONS_SCHEMA_VERSION` exists in Python and TypeScript

Once in `packages/financial-engine/.../assumptions.py`, once in
`apps/web/lib/assumptions.ts`. A drift here is silent: the browser sends a
version the API does not expect, and explicit zeros quietly become unknowns.

Guarded by `test_the_web_client_declares_the_same_version`, which reads the
`.ts` file and compares. That is a guard, not a fix.

**To clear:** generate the TypeScript constant from the Python source, or move
both behind `packages/shared-types` with a build step — which is the same
change item 8 needs.

### 8. Builds are pinned to `--webpack`

Turbopack is Next 16's default and cannot resolve `@atlas/shared-types`, whose
entry point is a source `.ts` file. Four approaches were tried and none worked;
see [`nextjs-upgrade.md`](nextjs-upgrade.md).

**To clear:** give `@atlas/shared-types` a real build step emitting
`dist/index.js` and `dist/index.d.ts`. Deferred because it introduces a
build-order dependency across the monorepo.

---

## Dependencies

### 9. React is held at 18.3.1

Next 16 supports React 19. React was deliberately not upgraded in the same
change as the framework, so that any breakage had one possible cause.

### 10. `eslint-config-next` is still 14.2.35

Version 16 requires ESLint ≥9 and therefore flat config. Linting works; the
config is simply older than the framework.

### 11. Ten development-only npm advisories

`vitest`, `vite`, `esbuild`, `eslint-config-next`, `glob`, `postcss`. None ship
in the production bundle (`npm audit --omit=dev` reports zero). Clearing them
requires `vitest@4` and the ESLint 9 migration above.

---

## Testing

### 12. SQLite is the default test engine

`make test` runs on SQLite, which differs from PostgreSQL on JSON handling,
NUMERIC precision, foreign-key enforcement and timezone semantics.
`make test-postgres` covers those 27 cases, but it is opt-in and skips
silently without `ATLAS_TEST_POSTGRES_URL`.

**To clear:** run `make test-postgres` in CI against a service container, so
the gap cannot reopen unnoticed.

### 13. No load, concurrency or query-plan testing

The indexes exist; no plan has been examined against a realistic row count, and
nothing has been tested under concurrent writes.

---

## Not debt

Recorded here because they look like omissions and are not:

- **`0003_investor_profile.sql` does nothing.** Harmless on a fresh database,
  correct on an existing one. Confusing to read, which is item 1's problem.
- **Unknown expenses overstate NOI.** Deliberate: omission is bounded and
  reported, whereas a guess would be indistinguishable from a known figure.
  See `financial-model.md`.
- **Atlas ships no default investor profile.** An unstated profile is unknown,
  and Atlas reports it as unknown rather than substituting an illustration.
