# atlas-web

The Atlas interface. Next.js App Router, TypeScript, Tailwind.

## What it does

The interface has one job the rest of the product depends on: **make every
assumption visible and editable, and show the calculation update immediately.**

- `/analyzer` — enter numbers, get all five strategies side by side. Nothing is
  saved unless you ask.
- `/properties/[id]` — the same analysis surface bound to a property, plus the
  assumption audit trail.
- `/settings` — the buy box that seeds every new analysis.

## How recalculation works

There is **no duplicated financial logic in the browser.** The engine is Python,
and the UI calls `POST /api/analyze` as the user types. That keeps a single
source of truth for every number: a figure on screen and the same figure in a
saved analysis cannot disagree, because both came from the same code.

The trade is a network round trip per change. `hooks/useAnalysis.ts` handles it:
requests are debounced, and each carries a sequence number so a slow earlier
response can never overwrite a newer one. Showing stale numbers in an
underwriting tool is worse than showing none.

## Conventions

**Money and ratios are strings.** They arrive from the API as decimal strings
and stay that way until display. Parsing to a float on the way in would
reintroduce the imprecision the engine exists to avoid.

**`null` is rendered as "—", never as 0.** A null DSCR means no debt; a null
cash-on-cash means no cash left in the deal. `lib/format.ts` enforces this, and
`tests/format.test.ts` protects it.

**Untouched assumptions are not sent.** `lib/assumptions.ts` tracks only the
fields a user actually overrode, so anything else uses the engine's provisional
default — and the UI can honestly tag it as one. Clearing a field restores the
default rather than sending a zero.

**Unbuilt features say so.** Markets, Contacts and parts of Projects render an
explicit note about what exists and what does not, instead of a mock that looks
functional.

## Running it

```bash
npm install
npm run dev          # http://localhost:3000, expects the API on :8000
npm run test         # Vitest unit tests
npm run test:e2e     # Playwright, boots the API and the app together
npm run typecheck
```

Set `NEXT_PUBLIC_API_URL` if the API is not on `localhost:8000`. Only public
values belong in `NEXT_PUBLIC_*` — those are compiled into the browser bundle.
No API key is ever sent to the browser.

On a machine with a pre-installed browser that Playwright may not download,
set `PLAYWRIGHT_CHROMIUM_PATH` to its executable.
