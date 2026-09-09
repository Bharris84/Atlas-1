# Atlas

An AI-assisted real-estate acquisition and investment intelligence platform.

Atlas exists to answer one question about a property:

> **Is this worth pursuing, and if so, what is the best way to structure the deal?**

It is not a wholesaling app. It models wholesale, fix & flip, buy & hold, BRRRR
and seller financing side by side, and tells you which one the property actually
supports — which is frequently not the one you had in mind.

---

## The rule that shapes everything else

**Deterministic code does the arithmetic. The AI only interprets it.**

```
property data
     ↓
financial engine   ← deterministic, tested, reproducible
     ↓
structured results
     ↓
AI interpretation  ← explains, challenges, questions. Never calculates.
     ↓
UI
```

A language model never determines a number Atlas publishes. It receives
completed calculations and explains them, challenges the assumptions behind
them, and says what is missing. If the AI provider is down, unavailable, or
never configured, every financial feature still works.

Alongside this sits a second rule: **every claim is labelled**.

| Label | Meaning |
|---|---|
| `FACT` | Verified from a source (appraisal, lease, contractor bid) |
| `ESTIMATE` | Derived from evidence, with a stated confidence |
| `INFERENCE` | Reasoned from other facts, not directly observed |
| `UNKNOWN` | Not known — and never quietly replaced with a zero |

Atlas does not fabricate missing information, and it does not present an
estimate as a verified fact.

---

## Repository layout

```
apps/
  web/                   Next.js + TypeScript + Tailwind front end
  api/                   FastAPI service, SQLAlchemy models, migrations
packages/
  financial-engine/      Deterministic underwriting maths (Python)
  scoring-engine/        Deal scoring, risk flags, verdicts (Python)
  data-providers/        Provider abstraction + RentCast (Python)
  ai-agents/             AI provider abstraction + agents (Python)
  shared-types/          TypeScript types shared with the web app
database/
  migrations/            SQL migrations
  seeds/                 Seed data
docs/                    Architecture and financial model documentation
infrastructure/          Deployment configuration
tests/                   Cross-cutting and end-to-end tests
```

---

## Status

| Phase | Scope | State |
|---|---|---|
| 1 | Deterministic financial engine + scoring engine | **Done** |
| 2 | PostgreSQL schema and API | **Done** |
| 3 | Next.js interface | **Done** |
| 4 | Engine connected to the UI | **Done** |
| 5 | Data provider abstraction + RentCast | **Done** |
| 6 | AI research agent | **Done** |
| 7 | AI strategist / underwriter | **Done** |
| 7.5 | Calibration: investor profile, capital efficiency, prediction-vs-actual | **Done** |
| 8 | CRM and lead management | Planned |
| 9 | Automated market discovery | Planned |
| 10 | Historical outcomes, predictive intelligence | Planned |
| 11 | SaaS / data product | Planned |

See [`docs/architecture.md`](docs/architecture.md) for the design,
[`docs/financial-model.md`](docs/financial-model.md) for every formula and
default assumption, and [`docs/calibration.md`](docs/calibration.md) for how to
check those assumptions against real deals.

---

## Getting started

Requirements: Python 3.10+, Node 18+, and PostgreSQL (or Supabase). Atlas runs
without PostgreSQL — it falls back to SQLite — and without any API keys.

```bash
# Backend: install the engines and the API, then run the tests
make install
make test

# Run the API (http://localhost:8000, docs at /docs)
make api

# Run the web app (http://localhost:3000)
make web
```

### Configuration

Copy `.env.example` to `.env`. Every external dependency is optional:

| Variable | Purpose | Required? |
|---|---|---|
| `ATLAS_DATABASE_URL` | PostgreSQL / Supabase connection | No — SQLite fallback |
| `SUPABASE_JWT_SECRET` | Verifies Supabase Auth tokens | No — dev auth fallback |
| `RENTCAST_API_KEY` | Property, value, rent and comp data | No — manual entry |
| `ATLAS_AI_PROVIDER` | `anthropic`, `openai` or `null` | No — defaults to `null` |
| `ANTHROPIC_API_KEY` | AI agent narration | No |

**API keys are read only by the backend.** The web app never sees them, and no
key is ever sent to the browser.

---

## The financial engine

The heart of Atlas. Pure Python, no I/O, no network, no database, no AI.

```python
from atlas_financial_engine import build_inputs, analyze_all_strategies

deal = build_inputs(
    purchase_price=150_000, arv=250_000, rehab=45_000, monthly_rent=1_800
)
comparison = analyze_all_strategies(deal)

comparison.recommended        # Strategy.FLIP
comparison.rationale          # why, in plain arithmetic-backed sentences
comparison.results[...]       # full breakdown per strategy
```

Notable decisions, each explained in `docs/financial-model.md`:

- **Wholesale is not the 70% rule.** Atlas models the end buyer's flip and
  solves for the highest price at which that buyer still hits their return,
  then subtracts the assignment fee and a risk buffer.
- **The best deal is not the biggest profit.** Ranking weights capital
  efficiency as heavily as profit, because early on the binding constraint is
  cash, not opportunity.
- **Undefined is not zero.** No debt means no DSCR. No cash in the deal means
  cash-on-cash is undefined, not infinite. These come back as `null`.
- **Unassessable is not average.** Scoring categories Atlas cannot evaluate are
  excluded and the coverage is reported, rather than padded with a guess.
- **Hard risks beat good scores.** An unverified ARV or a suspected structural
  problem forces human review regardless of the number.
- **Efficiency is not affordability.** Capital efficiency says how hard a
  dollar works; the investor profile says whether the dollars exist. Atlas
  reports them separately so you know which problem you have.

All assumptions are provisional defaults, visible and editable per deal, with
every change recorded in an audit trail. `python scripts/calibrate.py` compares
predictions against real outcomes and attributes the gap to a specific
assumption.

---

## Testing

```bash
make test          # Python: engines and API
make test-web      # Vitest unit tests
make test-e2e      # Playwright end-to-end
```

The financial engine is covered to ~98%, including the edge cases that matter
in practice: zero and negative cash flow, missing inputs, rehab exceeding ARV,
extreme interest rates, and byte-for-byte reproducibility of a saved analysis.
