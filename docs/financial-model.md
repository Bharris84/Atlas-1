# The Atlas financial model

Every formula Atlas uses, and every default assumption, in one place.

**All defaults below are provisional.** They are starting points chosen so the
engine returns an answer before anyone has tuned it. None of them are laws of
real estate. Every one is editable per deal, and every change is recorded in
the audit trail.

---

## Conventions

- All money is `Decimal`. Floats are never used, so results are reproducible
  across machines and over time.
- Intermediate arithmetic runs at full precision; rounding happens once, at the
  output boundary — money to cents, rates to 6dp, ratios to 4dp.
- **Missing means missing.** An unknown rent is `None`, never `0`. A property
  with no rent estimate is not a property that rents for nothing.
- **Undefined means undefined.** Division by zero returns `None`, which reaches
  the UI as `null` and renders as "—", never as `0%`.

---

## Shared cost model

Wholesale, flip and BRRRR all price the same underlying project, so they share
one cost model.

```
acquisition closing   = purchase price x 2%          + flat
rehab total           = rehab x (1 + contingency)
holding costs         = monthly holding x months
  monthly holding     = taxes/12 + insurance/12 + HOA + utilities + other
financing costs       = points + interest + lender fees
  loan                = purchase x LTP + rehab total x LTR
  interest            = purchase loan x f + rehab loan x f x draw factor
selling costs         = sale price x (6% commission + 2% closing) + flat

total project cost    = purchase + rehab total + acquisition closing
                      + holding + financing + selling + miscellaneous
total basis           = total project cost - selling costs
cash required         = (purchase - purchase loan) + (rehab total - rehab loan)
                      + acquisition closing + holding + financing + misc
```

Two details worth stating:

**Rehab draw factor (default 0.60).** Hard-money rehab funds draw
progressively as work is completed, so charging full interest on the entire
rehab loan for the whole hold overstates the cost. Atlas charges interest on
the average outstanding balance.

**Costs are linear in purchase price.** Acquisition closing, points and
interest all scale with the price, so "what is the most I can pay?" is a
solvable equation rather than a search. Atlas solves it exactly, which is what
makes max-price answers reproducible. The equivalence between the linear form
and the direct calculation is asserted in the test suite.

---

## Wholesale

Atlas deliberately **does not use the 70% rule**. That rule is a compressed
approximation, and it breaks in exactly the markets Atlas targets: low price
points where fixed costs dominate, and heavy rehabs where the rehab-to-ARV
ratio is far from typical.

Instead, wholesale is underwritten from the end buyer's deal:

```
1. Model the flip the end buyer would actually be doing.
2. Solve for the highest price at which that buyer still earns their
   required profit.                      -> maximum end-buyer purchase price
3. maximum end-buyer purchase price
     - target assignment fee
     - risk buffer                       -> maximum allowable contract price
```

Then, given an actual contract price:

```
spread                 = maximum end-buyer price - contract price
estimated assignment   = max(spread - risk buffer, 0)
wholesale profit       = estimated assignment - transaction costs
```

The risk buffer exists because the buyer's own inspection will find things
ours did not, and a contract that cannot be assigned is worth less than
nothing.

| Assumption | Default |
|---|---|
| Target assignment fee | $10,000 |
| Buyer profit target | 15% of ARV |
| Buyer profit floor | $20,000 |
| Risk buffer | 2% of ARV |
| Buyer rehab contingency | 15% |
| Buyer holding period | 6 months |

The **profit floor** matters on cheap houses: 15% of an $80,000 ARV is
$12,000, which no investor will take on a full rehab. The floor stops Atlas
from producing an offer no buyer would accept.

---

## Fix & flip

```
net profit = ARV
           - purchase price
           - rehab (incl. contingency)
           - acquisition closing costs
           - financing costs
           - holding costs
           - selling costs
           - miscellaneous
```

```
ROI             = net profit / cash invested      (not / project cost)
profit margin   = net profit / ARV
annualised ROI  = ROI x 12 / holding months
max price       = min(price meeting profit target, price meeting ROI target)
```

**ROI is measured against cash invested, not total project cost.** With
leverage those are very different numbers, and cash invested is the one that
governs how many deals can run at once.

| Assumption | Default |
|---|---|
| Minimum net profit | $30,000 |
| Minimum ROI | 20% |
| Rehab contingency | 15% |
| Holding period | 6 months |
| Financing | Hard money: 90% of purchase, 100% of rehab, 11%, 2 points, $1,500 fees |

---

## Buy & hold

```
gross scheduled rent  = monthly rent x 12
  - vacancy
= effective gross income
  - management, maintenance, CapEx, taxes, insurance, HOA, other
= NOI
  - debt service
= cash flow
```

```
cap rate       = NOI / purchase price
DSCR           = NOI / annual debt service        (None when there is no debt)
cash-on-cash   = annual cash flow / cash invested
max price      = min(price meeting cash flow, DSCR and CoC targets)
```

Two conventions, stated because investors differ and the difference is
material:

- **Management is charged on collected rent** (effective gross income), which
  is how management agreements are actually written.
- **Maintenance and CapEx are charged on gross scheduled rent**, because a
  vacant unit still ages.

| Assumption | Default |
|---|---|
| Vacancy | 5% |
| Management | 8% of collected rent |
| Maintenance | 5% of gross rent |
| CapEx | 5% of gross rent |
| Minimum cash flow | $300/month |
| Minimum cash-on-cash | 8% |
| Target DSCR | 1.25 |
| Financing | Conventional: 25% down, 7%, 30-year |

---

## BRRRR

```
total project cost = purchase + rehab + closing + holding + financing
new loan           = post-rehab value x refinance LTV
cash returned      = new loan - refinance costs - acquisition payoff
cash left in deal  = cash invested - cash returned
equity created     = post-rehab value - total basis
```

**Cash left in the deal is the number that decides whether BRRRR is right.**
A BRRRR that traps $60,000 is worse for an early-stage operator than a flip
that returns everything, even if it creates more paper equity.

For the same reason, BRRRR's reported *profit* is its annual cash flow, not the
equity it creates. Equity created is real but unrealised; counting it as profit
would double-count it against a flip, where the same equity is actually
converted to cash.

| Assumption | Default |
|---|---|
| Refinance LTV | 75% |
| Maximum cash left in deal | $25,000 |
| Minimum equity after refinance | 20% |
| Refinance closing costs | 2% of the new loan |
| Seasoning period | 6 months |
| Refinance terms | 7.5%, 30-year |

---

## Seller financing

Models buying on terms and holding as a rental.

```
down payment      = price x down payment %
financed amount   = price - down payment
monthly payment   = standard amortisation of the financed amount
balloon balance   = remaining balance at the balloon date
cash flow         = NOI - annual debt service
```

The balloon is modelled explicitly and warned about up front. A five-year
balloon is a five-year commitment to refinance or sell, and the amount coming
due is something the operator must see now, not discover later.

| Assumption | Default |
|---|---|
| Down payment | 10% |
| Interest rate | 6% |
| Amortisation | 30 years |
| Balloon | 5 years |
| Closing costs | 1% |

---

## Strategy ranking

Strategies are scored on seven dimensions against **absolute** benchmarks from
the buy box — not relative to each other. Relative normalisation would make the
best of five bad options look excellent.

| Dimension | Weight |
|---|---|
| Profit | 25% |
| Capital efficiency | 25% |
| ROI | 15% |
| Cash flow | 10% |
| Equity creation | 10% |
| Risk | 10% |
| Time to liquidity | 5% |

Capital efficiency carries as much weight as profit. Early on, the binding
constraint is cash, not opportunity.

Scoring rules that keep the ranking honest:

- Hitting a target scores 50; hitting twice the target scores 100.
- A strategy needing **no capital** scores full marks on capital efficiency and
  ROI — but only if it actually earns a profit. Return on zero cash is
  undefined, not zero, and scoring it as zero would punish a strategy for the
  very property that makes it attractive.
- Missing the buy box costs 15 points rather than disqualifying, so near-misses
  that a small price change would rescue stay visible.
- An unmeasured dimension scores zero. Atlas never credits what it cannot see.

---

## Deal scoring

| Category | Weight | Assessable in V0.1? |
|---|---|---|
| Financial potential | 25% | Yes |
| Equity | 20% | Yes |
| Seller situation | 15% | **No** |
| Market | 15% | **No** |
| Property | 10% | Yes |
| Exit options | 10% | Yes |
| Risk | 5% | Yes |

**Unassessable categories are excluded, not guessed.** Scoring an unknown as
zero would make every deal look bad; scoring it as average would invent
information. Atlas excludes it, renormalises the remaining weights, and reports
`coverage` — the share of the rubric actually assessed.

| Score | Verdict |
|---|---|
| 80–100 | PURSUE |
| 60–79 | INVESTIGATE |
| below 60 | PASS |

Two overrides sit above the score:

1. **A blocking risk flag forces `HUMAN_REVIEW_REQUIRED`**, regardless of the
   score. Unverified ARV, suspected title defect, structural uncertainty,
   environmental concern, severe financing uncertainty, heavy rehab resting on
   a guess, or no viable strategy at all.
2. **Coverage below 65% cannot reach PURSUE.** In V0.1 the ceiling is 70%, so
   in practice this means Atlas will not tell you to chase a house it knows
   nothing about physically.

The score is always still reported alongside an override. The override changes
the decision; it does not hide the arithmetic.

---

## Confidence

Every major estimate is rated on how well supported it is, separately from the
estimate itself. This prevents false precision: a $312,450 ARV from an
automated valuation is not the same claim as the same figure from five recent,
highly similar closed sales.

**ARV**

| Basis | Confidence |
|---|---|
| Appraisal | HIGH (`FACT`) |
| 4+ comps, similarity ≥ 0.75, within 180 days | HIGH |
| 2–3 comps, or weaker similarity/recency | MEDIUM |
| Fewer than 2 comps | LOW |
| Broker price opinion | MEDIUM |
| Automated valuation | LOW |
| List price | LOW (`INFERENCE` — an asking price is not a value) |
| Nothing recorded | LOW (`UNKNOWN`) |

**Rehab**: contractor bid → HIGH (`FACT`); line-item scope → HIGH;
walkthrough → MEDIUM; per-square-foot rule of thumb → LOW; nothing → LOW.

**Rent**: lease in place or rent roll → HIGH (`FACT`); 3+ rental comps → HIGH;
1–2 comps → MEDIUM; automated estimate → MEDIUM; nothing → LOW.

A low/high range spanning more than 15% of its midpoint costs one confidence
level, and says so.

**Combination is weakest-link.** An analysis built on a HIGH-confidence ARV and
a LOW-confidence rehab is a LOW-confidence analysis. Every downgrade carries a
reason string, shown verbatim in the UI.
