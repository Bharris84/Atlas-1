# atlas-financial-engine

The deterministic core of Atlas. Given the same inputs it returns the same
outputs, on any machine, forever — which is what makes an analysis auditable
months after it was run.

This package has **no dependencies**. It does not touch the network, a
database, or an AI provider.

```python
from atlas_financial_engine import build_inputs, analyze_all_strategies

deal = build_inputs(
    purchase_price=150_000, arv=250_000, rehab=45_000, monthly_rent=1_800
)
comparison = analyze_all_strategies(deal)
print(comparison.recommended)
print("\n".join(comparison.rationale))
```

## Layout

| Module | Responsibility |
|---|---|
| `money` | Decimal primitives, rounding policy, safe division |
| `loans` | Payments, balances, interest, amortisation schedules, DSCR |
| `costs` | Shared project cost model + its linear form for max-price solving |
| `confidence` | How well supported each estimate is, and why |
| `inputs` | `DealInputs` value object, serialisation, missing-field detection |
| `assumptions` | The buy box. Every default is provisional and overridable |
| `results` | The common result shape every strategy returns |
| `strategies/` | Wholesale, flip, buy & hold, BRRRR, seller financing |
| `strategy_engine` | Runs all five, scores and ranks them, recommends one |

## Running the tests

```bash
pip install -e ".[dev]"
pytest --cov=atlas_financial_engine
```

The suite covers the arithmetic to ~98%, and asserts the properties that make
the engine trustworthy rather than merely working:

- **Round trips.** Buying at a solved maximum price produces exactly the target
  profit, ROI, or cash-left figure the solver was given.
- **Model equivalence.** The linear cost model used for solving agrees with the
  direct calculation at every price and under every financing type.
- **Determinism.** The same inputs serialise to byte-identical JSON, and a
  stored analysis reproduces exactly when reopened.
- **No float contamination.** The output tree is walked to assert no float ever
  reaches the API boundary.
- **Edge cases.** Zero and negative cash flow, missing inputs, rehab exceeding
  ARV, eight-figure deals, 0% and 99% interest rates.
