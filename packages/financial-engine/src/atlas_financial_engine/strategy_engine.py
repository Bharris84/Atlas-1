"""Strategy engine — run every strategy, then rank them honestly.

The ranking deliberately does NOT sort by gross profit. A flip that nets
$45,000 on $95,000 of cash over nine months is not obviously better than a
wholesale that nets $12,000 on almost no cash in three weeks — and for an
operator whose binding constraint is capital, it is usually worse.

Each strategy is scored on seven dimensions against ABSOLUTE benchmarks drawn
from the buy box, not relative to the other strategies. That matters: relative
normalisation would make the best of five bad options look excellent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from .assumptions import StrategyRankingWeights
from .capital_efficiency import CapitalEfficiency, compute_all_capital_efficiency
from .enums import Confidence, Strategy
from .inputs import DealInputs
from .money import D, MONTHS_PER_YEAR, Numeric, ZERO, ratio, safe_div
from .results import StrategyResult
from .strategies.brrrr import analyze_brrrr
from .strategies.buy_hold import analyze_buy_hold
from .strategies.flip import analyze_flip
from .strategies.seller_finance import analyze_seller_finance
from .strategies.wholesale import analyze_wholesale

# A strategy that misses its own buy box is penalised rather than disqualified.
# Disqualifying would hide near-miss deals that a small price change rescues.
BUY_BOX_MISS_PENALTY = D("15")

# Execution risk that is inherent to the strategy itself, independent of this
# particular property. Wholesaling assigns a contract; BRRRR requires a rehab,
# a tenant and an appraiser to all cooperate.
EXECUTION_RISK_SCORE: Dict[Strategy, Decimal] = {
    Strategy.WHOLESALE: D("90"),
    Strategy.FLIP: D("60"),
    Strategy.BUY_HOLD: D("75"),
    Strategy.BRRRR: D("50"),
    Strategy.SELLER_FINANCE: D("70"),
}

CONFIDENCE_SCORE: Dict[Confidence, Decimal] = {
    Confidence.HIGH: D("100"),
    Confidence.MEDIUM: D("65"),
    Confidence.LOW: D("35"),
}


def _capped(actual: Optional[Numeric], target: Numeric, cap_multiple: str = "2") -> Decimal:
    """Score an actual against a target on a 0-100 scale.

    Hitting the target scores 50; hitting ``cap_multiple`` times the target
    scores 100. Missing entirely scores 0. Unknown scores 0 — an unmeasured
    dimension is never credited.
    """
    if actual is None:
        return ZERO
    t = D(target)
    if t <= 0:
        return ZERO
    r = D(actual) / t
    if r <= 0:
        return ZERO
    cap = D(cap_multiple)
    if r >= cap:
        return D("100")
    return (r / cap) * D("100")


def _time_score(months: Optional[int]) -> Decimal:
    """Shorter time to liquidity scores higher. ``None`` means illiquid."""
    if months is None:
        return D("20")
    if months <= 1:
        return D("100")
    if months <= 3:
        return D("85")
    if months <= 6:
        return D("70")
    if months <= 12:
        return D("50")
    if months <= 24:
        return D("35")
    return D("20")


def _roi_score(result: StrategyResult, target_roi: Decimal) -> Decimal:
    """Return on cash invested.

    When a strategy commits no capital, ROI is undefined rather than zero.
    Scoring that as a zero would penalise a strategy for the very property —
    needing no money — that makes it attractive, so a profitable no-capital
    strategy scores full marks here.
    """
    if result.roi is not None:
        return _capped(result.roi, target_roi)
    committed = result.cash_required
    if result.profit is not None and result.profit > 0 and (
        committed is None or committed <= 0
    ):
        return D("100")
    return ZERO


def _capital_efficiency_score(result: StrategyResult) -> Decimal:
    """Profit per dollar of cash committed.

    A strategy that requires no capital is maximally capital-efficient, but
    only if it actually produces a profit — a zero-cash strategy earning
    nothing scores zero, not 100.
    """
    profit = result.profit
    cash = result.cash_required
    if profit is None or profit <= 0:
        return ZERO
    if cash is None or cash <= 0:
        return D("100")
    return _capped(safe_div(profit, cash), D("0.5"))


@dataclass(frozen=True)
class StrategyScore:
    strategy: Strategy
    score: Decimal
    components: Dict[str, Decimal]
    meets_criteria: bool
    penalty_applied: Decimal

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "score": str(self.score),
            "components": {k: str(v) for k, v in self.components.items()},
            "meets_criteria": self.meets_criteria,
            "penalty_applied": str(self.penalty_applied),
        }


def score_strategy(
    result: StrategyResult,
    inputs: DealInputs,
    weights: Optional[StrategyRankingWeights] = None,
) -> StrategyScore:
    a = inputs.assumptions
    w = weights or a.ranking

    # Profit benchmarks differ by strategy because the strategies produce
    # structurally different kinds of profit.
    if result.strategy == Strategy.WHOLESALE:
        profit_target: Decimal = a.wholesale.target_assignment_fee
    elif result.strategy == Strategy.FLIP:
        profit_target = a.flip.minimum_net_profit
    else:
        # Hold strategies (including BRRRR) realise profit as annual cash flow.
        profit_target = a.rental.minimum_monthly_cash_flow * MONTHS_PER_YEAR

    arv = inputs.effective_arv
    equity_target = (
        D(arv) * a.brrrr.minimum_equity_percent if arv is not None else D("30000")
    )

    components: Dict[str, Decimal] = {
        "profit": _capped(result.profit, profit_target),
        "capital_efficiency": _capital_efficiency_score(result),
        "roi": _roi_score(result, a.flip.minimum_roi),
        "cash_flow": _capped(result.monthly_cash_flow, a.rental.minimum_monthly_cash_flow),
        "equity_creation": _capped(result.equity_created, equity_target),
        "time_to_liquidity": _time_score(result.time_to_liquidity_months),
        "risk": (
            CONFIDENCE_SCORE[result.confidence] * D("0.6")
            + EXECUTION_RISK_SCORE[result.strategy] * D("0.4")
        ),
    }

    total = (
        components["profit"] * w.profit
        + components["capital_efficiency"] * w.capital_efficiency
        + components["roi"] * w.roi
        + components["cash_flow"] * w.cash_flow
        + components["equity_creation"] * w.equity_creation
        + components["time_to_liquidity"] * w.time_to_liquidity
        + components["risk"] * w.risk
    )

    penalty = ZERO if result.meets_criteria else BUY_BOX_MISS_PENALTY
    final = total - penalty
    if final < 0:
        final = ZERO

    return StrategyScore(
        strategy=result.strategy,
        score=ratio(final),
        components={k: ratio(v) for k, v in components.items()},
        meets_criteria=result.meets_criteria,
        penalty_applied=penalty,
    )


@dataclass(frozen=True)
class StrategyComparison:
    results: Dict[Strategy, StrategyResult]
    scores: List[StrategyScore]
    recommended: Optional[Strategy]
    alternative: Optional[Strategy]
    rationale: List[str]
    viable_exit_count: int
    overall_confidence: Confidence
    missing_information: List[str] = field(default_factory=list)
    # Provisional, additive metric. Reported alongside the ranking; it does NOT
    # feed the ranking or the deal score. See capital_efficiency.py.
    capital_efficiency: Dict[Strategy, CapitalEfficiency] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategies": {k.value: v.to_dict() for k, v in self.results.items()},
            "ranking": [s.to_dict() for s in self.scores],
            "recommended_strategy": self.recommended.value if self.recommended else None,
            "alternative_strategy": self.alternative.value if self.alternative else None,
            "rationale": list(self.rationale),
            "viable_exit_count": self.viable_exit_count,
            "overall_confidence": self.overall_confidence.value,
            "missing_information": list(self.missing_information),
            "capital_efficiency": {
                k.value: v.to_dict() for k, v in self.capital_efficiency.items()
            },
        }


STRATEGY_LABELS = {
    Strategy.WHOLESALE: "Wholesale",
    Strategy.FLIP: "Fix & flip",
    Strategy.BUY_HOLD: "Buy & hold",
    Strategy.BRRRR: "BRRRR",
    Strategy.SELLER_FINANCE: "Seller financing",
}


def _fmt_money(value: Optional[Decimal]) -> str:
    return f"${value:,.0f}" if value is not None else "unknown"


def _fmt_pct(value: Optional[Decimal]) -> str:
    return f"{value * 100:.1f}%" if value is not None else "unknown"


def _build_rationale(
    recommended: Optional[Strategy],
    alternative: Optional[Strategy],
    results: Dict[Strategy, StrategyResult],
    scores: List[StrategyScore],
) -> List[str]:
    """Deterministic, arithmetic-backed rationale.

    This is intentionally computed rather than generated. The AI strategist
    later writes prose around these facts; it never replaces them.
    """
    lines: List[str] = []
    if recommended is None:
        lines.append(
            "No strategy could be evaluated with the information provided."
        )
        return lines

    top = results[recommended]
    lines.append(
        f"{STRATEGY_LABELS[recommended]} ranks first: "
        f"{_fmt_money(top.profit)} profit on {_fmt_money(top.cash_required)} of cash"
        + (f", ROI {_fmt_pct(top.roi)}" if top.roi is not None else "")
        + (
            f", {top.time_to_liquidity_months} months to liquidity"
            if top.time_to_liquidity_months is not None
            else ""
        )
        + "."
    )
    if not top.meets_criteria:
        unmet = [c.label for c in top.criteria if not c.met]
        lines.append(
            "It ranks first while still missing part of the buy box: "
            + ", ".join(unmet)
            + "."
        )
    if alternative is not None:
        alt = results[alternative]
        lines.append(
            f"{STRATEGY_LABELS[alternative]} is the alternative: "
            f"{_fmt_money(alt.profit)} profit, {_fmt_money(alt.cash_required)} of cash."
        )
    for score in scores:
        result = results[score.strategy]
        if score.strategy == recommended:
            continue
        if not result.meets_criteria and result.criteria:
            unmet = [c.label for c in result.criteria if not c.met]
            if unmet:
                lines.append(
                    f"{STRATEGY_LABELS[score.strategy]} falls short on: "
                    + ", ".join(unmet)
                    + "."
                )
    if top.confidence != Confidence.HIGH:
        lines.append(
            f"Confidence in this recommendation is {top.confidence.value}. "
            "The ranking is only as good as the ARV and rehab inputs behind it."
        )
    return lines


def analyze_all_strategies(inputs: DealInputs) -> StrategyComparison:
    """Run every strategy model and rank the viable ones."""
    results: Dict[Strategy, StrategyResult] = {
        Strategy.WHOLESALE: analyze_wholesale(inputs),
        Strategy.FLIP: analyze_flip(inputs),
        Strategy.BUY_HOLD: analyze_buy_hold(inputs),
        Strategy.BRRRR: analyze_brrrr(inputs),
        Strategy.SELLER_FINANCE: analyze_seller_finance(inputs),
    }

    viable = [r for r in results.values() if r.viable]
    scores = sorted(
        (score_strategy(r, inputs) for r in viable),
        key=lambda s: s.score,
        reverse=True,
    )

    recommended = scores[0].strategy if scores else None
    alternative = scores[1].strategy if len(scores) > 1 else None

    # "Viable exits" counts strategies that both compute AND clear their buy
    # box. Optionality is what protects a deal when plan A stops working.
    viable_exit_count = sum(1 for r in viable if r.meets_criteria)

    overall_confidence = (
        Confidence.weakest(*[r.confidence for r in viable]) if viable else Confidence.LOW
    )

    missing = sorted({m for r in results.values() for m in r.missing_inputs})
    missing.extend(m for m in inputs.missing_fields() if m not in missing)

    # Computed for every strategy, reported next to the ranking, and
    # deliberately not fed back into it. Wiring it into the ranking is a
    # decision to make against calibration evidence, not in advance of it.
    capital_efficiency = compute_all_capital_efficiency(
        results,
        profile=inputs.investor_profile if inputs.investor_profile.is_stated else None,
        target_return=inputs.assumptions.flip.minimum_roi,
    )

    return StrategyComparison(
        results=results,
        scores=scores,
        recommended=recommended,
        alternative=alternative,
        rationale=_build_rationale(recommended, alternative, results, scores),
        viable_exit_count=viable_exit_count,
        overall_confidence=overall_confidence,
        missing_information=sorted(set(missing)),
        capital_efficiency=capital_efficiency,
    )
