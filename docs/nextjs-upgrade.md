# Next.js 16 upgrade — compatibility record

Upgraded `next` 14.2.35 → **16.3.4**, holding React at **18.3.1**.

## Why

`npm audit` reported a CRITICAL advisory against every Next version in the
range `9.3.4-canary.0 … 16.3.0-preview.10` (DoS via Image Optimizer
`remotePatterns`). 15.x is inside that range; **only 16.3.4 is fixed.**

Atlas uses neither `next/image` nor `remotePatterns`, so practical exposure to
that specific advisory was assessed as nil — but carrying a known-vulnerable
framework version is not a position worth defending.

**Result: `npm audit --omit=dev` now reports 0 vulnerabilities.**

## React was NOT upgraded

`next@16.3.4` declares `react: "^18.2.0 || ^19.0.0"`. React 19 is **not**
required. An earlier status report stated otherwise; that was wrong.

## Migration surface (why this was cheap)

Atlas uses only `next/link` and the `next/navigation` client hooks
(`useRouter`, `usePathname`, `useParams`). 15 of 16 components are
`"use client"`.

Not used, and therefore not affected: async `params`/`searchParams`,
`cookies()`, `headers()`, middleware, API routes, server actions, `next/image`,
`next/font`.

## Breaking changes actually encountered

| Change | Impact | Resolution |
|---|---|---|
| **Turbopack is the default builder** | Cannot resolve `@atlas/shared-types`, whose entry point is a source `.ts` file. Four approaches were tried — `file:` dependency, `exports` map, relative and absolute `turbopack.resolveAlias` — none resolved it | Build and dev pinned to `--webpack`, which works correctly. **See technical debt below** |
| **`eslint` key removed from `next.config.mjs`** | Config warning | Key removed |
| **`next lint` removed** | `npm run lint` broke | Script now invokes `eslint` directly |
| **Cross-origin dev requests blocked by default** | Client components never hydrated when the e2e suite drove the app over `127.0.0.1`; 13 of 15 e2e tests failed with empty pages. Development only — production builds unaffected | `allowedDevOrigins: ["127.0.0.1", "localhost"]` |

## Verification

- `tsc --noEmit` — clean
- `next build --webpack` — 12/12 routes built
- `eslint` — no warnings or errors
- Vitest — 72/72
- Playwright — 15/15
- `npm audit --omit=dev` — 0 vulnerabilities

## Technical debt created

1. **Builds are pinned to webpack.** Turbopack is Next's default and webpack
   support will not last forever. The durable fix is to give
   `@atlas/shared-types` a real build step emitting `dist/index.js` +
   `dist/index.d.ts`, so it resolves as an ordinary package under any bundler.
   Deferred: it introduces a build-order dependency across the monorepo.
2. **10 development-only advisories remain** (`vitest`, `vite`, `esbuild`,
   `eslint-config-next`, `glob`, `postcss`). None ship in the production
   bundle. Clearing them requires `vitest@4` and `eslint@9` (flat config).
3. **`eslint-config-next` is still 14.2.35.** Version 16 requires ESLint ≥9,
   which means migrating to flat config. Linting works; the config is simply
   older than the framework.
