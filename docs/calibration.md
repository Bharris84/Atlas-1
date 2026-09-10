# Calibrating Atlas

Atlas's arithmetic is correct and tested to 98%. That is a different claim from
"Atlas's answers are right", because an answer is only as good as the
assumptions behind it. A 15% rehab contingency, a 6% commission and a 15%
end-buyer profit target are provisional guesses until real deals say otherwise.

Calibration measures that gap. It is deterministic: no machine learning, no
fitting, no hidden adjustment. It re-runs the engine with known actual values
substituted in, one at a time, and reports how far each substitution moves the
prediction. That isolates which assumption was wrong.

---

## Running it

```bash
cp calibration/deals.example.json calibration/deals.json
# edit calibration/deals.json with deals you actually know the outcome of
python scripts/calibrate.py calibration/deals.json
python scripts/calibrate.py calibration/deals.json --json   # machine-readable
```

With no argument it runs the bundled example, which is **entirely
hypothetical** and says nothing about Atlas's real accuracy. It exists to show
the output format.

---

## What to enter

Each deal has two halves.

**`inputs`** — what you *would have entered in Atlas before the deal*. Not what
you know now. The point is to test the prediction you would actually have made,
so resist correcting it with hindsight.

**`actual`** — what really happened.

```json
{
  "name": "412 Magnolia Street",
  "inputs": {
    "purchase_price": "150000",
    "arv": "250000",
    "rehab": "45000",
    "monthly_rent": "1800",
    "evidence": { "arv_basis": "comparable_sales", "comp_count": 3 },
    "assumptions": {
      "schema_version": 1,
      "holding": {
        "annual_taxes": "2400",
        "annual_insurance": "1800",
        "monthly_hoa": "0",
        "monthly_utilities": "150"
      }
    }
  },
  "actual": {
    "strategy_executed": "flip",
    "actual_profit": "-18300",
    "actual_sale_price": "232000",
    "actual_rehab": "47500",
    "actual_holding_months": 8,
    "notes": "A $2,500 buyer credit at closing is not modelled by Atlas."
  }
}
```

**Fill in the whole expense sheet, including the zeros.** Taxes, insurance, HOA
and utilities have no defaults; anything left out is treated as unknown and
omitted from the arithmetic, which inflates the *predicted* profit and makes the
report blame the gap on whichever factor you did supply. Write `"0"` where an
expense genuinely did not apply — that is an answer, and it is a different one
from leaving the field out. `"schema_version": 1` tells Atlas the file speaks
the current assumption semantics; without it a `"0"` is read the old way, as
"not filled in".

**`actual_profit` must be on the same basis as the strategy's profit.** An exit
profit for wholesale and flip; an **annual cash flow** for buy & hold, BRRRR and
seller finance. Mixing the two produces a meaningless comparison, so the report
states which basis it used for every deal.

Every other `actual_*` field is optional. Supply what you know — each one you
provide is one more factor the report can attribute the gap to.

---

## Reading the output

```
  Atlas prediction  : $7,882
  Actual outcome    : -$18,300
  Difference        : -$26,182  (-332.2%)

  Which assumption caused the difference:
    ARV / sale price      250000 -> 232000        -$16,560
    Holding period             6 -> 8              -$4,044
    Rehab                  45000 -> 47500          -$3,027

  Explained by wrong inputs : -$23,663
  Factor interaction        : -$32
  Unexplained residual      : -$2,519   <- cost model, not estimates
```

**Attribution** answers "was it my ARV or my rehab that was off?" Each line is
the engine re-run with that one input replaced by its actual, so the impact is
isolated. Note the ARV impact is $16,560 rather than the full $18,000 gap —
selling costs fall with the sale price, so part of the miss pays for itself.

**Factor interaction** is reported because one-at-a-time impacts do not sum
exactly when factors affect each other. Hiding it would make the attributions
look more precise than they are.

**Unexplained residual is the number that matters most.** It is what remains
after *every known input is corrected*. It cannot be blamed on a bad estimate,
so it means the cost model itself is wrong — a real cost Atlas is not charging,
or one it overstates. In the example above, a $2,500 closing credit Atlas does
not model.

### The summary

```
  Mean signed error         : -$10,148   (negative = Atlas is optimistic)
  Mean unexplained residual : -$698
```

A **mean signed error** close in size to the mean absolute error means the
errors all point the same way. That is bias, not noise, and bias is fixable —
the report says so explicitly when it detects one.

A consistently negative **mean unexplained residual** says Atlas is missing a
real cost on every deal. Fix that before touching any estimate.

---

## What to do with the result

Work in this order, because each step can create the appearance of a problem in
the next:

1. **A non-zero residual first.** A missing cost distorts every deal. Add it to
   the cost model (`packages/financial-engine/src/atlas_financial_engine/costs.py`)
   or to the transaction assumptions.
2. **Then systematic bias.** If Atlas consistently overstates profit by ~$10k,
   the buy-box defaults are too generous. Raise the rehab contingency, the
   holding period, or the selling costs — whichever the attribution table
   implicates most.
3. **Then the largest single factor.** If ARV dominates, the problem is the comp
   selection process, not the engine. Tighten what counts as a comp before
   changing any number.

**Change one thing at a time and re-run.** Changing three assumptions at once
and seeing the error fall tells you nothing about which change helped.

---

## Honest limits

- **Three deals demonstrate the method. They do not validate it.** With three
  data points a $10,000 mean error could be one unusual deal. The report warns
  about sample size below ten and refuses to imply more than it knows.
- **Attribution assumes the engine's structure is right.** It measures how
  wrong the *inputs* were. If the cost model is missing something structural,
  that lands in the residual — which is precisely why the residual is reported
  separately rather than folded into the factors.
- **Nothing here is automatic.** Calibration reports; a human decides what to
  change. Atlas does not tune its own assumptions, and it will not until there
  is enough history for that to mean something.
- **Hypothetical deals prove nothing.** The bundled example is invented. Real
  outcomes are the only input that makes this exercise worth doing.
