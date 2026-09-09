"""Capital efficiency — a provisional, transparent metric.

The question this answers is not "how much does this deal make?" but "how hard
does each dollar of my capital work, and for how long is it stuck?"

Two deals earning $20,000 are not equally good. One that ties up $90,000 for a
year is a worse use of capital than one that ties up $25,000 for four months,
and for an operator whose binding constraint is cash, that difference decides
which deals are even possible.

Design constraints this module holds itself to:

* **Deterministic.** Same inputs, same output, always. No model, no heuristics
  that cannot be written down.
* **Transparent.** Every input used is emitted alongside the result in
  ``inputs``, and ``formula`` states in plain language how the score was
  derived. A user must be able to recompute this by hand.
* **Additive.** This does NOT replace or alter the deal score, and it is
  deliberately NOT wired into strategy ranking yet. It is a second opinion,
  reported next to the existing numbers, pending calibration against real deals.

Efficiency and affordability are kept apart on purpose. A deal can be a superb
use of capital and still be one the investor cannot fund. ``score`` answers the
first; ``within_capital_limit`` answers the second. Collapsing them into one
number would hide which problem you actually have.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from .enums import Confidence, Strategy
from .investor import InvestorProfile
from .money import D, MONTHS_PER_YEAR, Numeric, ZERO, money, ratio, safe_div
from .results import StrategyResult

# Hitting the target return scores 50; twice the target scores 100. The same
# convention the strategy ranker already uses, so the two are readable together.
SCORE_AT_TARGET = D("50")
CAP_MULTIPLE = D("2")

# Used only when neither the investor nor the deal assumptions state one.
PROVISIONAL_TARGET_RETURN = D("0.20")


class ProfitHorizon(str, Enum):
    """Over what period a strategy's profit is realised.

    This distinction is what stops the metric from comparing unlike things. A
    flip's profit lands once, at exit. A rental's profit is an annual figure
    that repeats. Annualising the second one again would double it.
    """

    # Profit is realised once, at exit, after which the capital is free.
    TRANSACTIONAL = "transactional"
    # Profit is an annual figure and the capital stays committed.
    ANNUAL_INCOME = "annual_income"


HORIZON_BY_STRATEGY: Dict[Strategy, ProfitHorizon] = {
    Strategy.WHOLESALE: ProfitHorizon.TRANSACTIONAL,
    Strategy.FLIP: ProfitHorizon.TRANSACTIONAL,
    Strategy.BUY_HOLD: ProfitHorizon.ANNUAL_INCOME,
    Strategy.BRRRR: ProfitHorizon.ANNUAL_INCOME,
    Strategy.SELLER_FINANCE: ProfitHorizon.ANNUAL_INCOME,
}


@dataclass(frozen=True)
class CapitalEfficiency:
    """How hard capital works in one strategy, with every input on show."""

    strategy: Strategy
    horizon: ProfitHorizon
    horizon_months: Optional[int]

    capital_deployed: Optional[Decimal]
    profit: Optional[Decimal]

    return_on_capital: Optional[Decimal]
    capital_velocity: Optional[Decimal]
    annualized_return_on_capital: Optional[Decimal]
    profit_per_1k_deployed: Optional[Decimal]
    capital_recycled_percent: Optional[Decimal]

    share_of_available_capital: Optional[Decimal]
    within_capital_limit: Optional[bool]
    capital_ceiling: Optional[Decimal]

    capital_free: bool
    computable: bool
    score: Optional[Decimal]
    score_target: Optional[Decimal]
    formula: str
    notes: List[str] = field(default_factory=list)
    inputs: Dict[str, Optional[str]] = field(default_factory=dict)
    confidence: Confidence = Confidence.LOW

    def to_dict(self) -> Dict[str, Any]:
        def s(value: Optional[Decimal]) -> Optional[str]:
            return str(value) if value is not None else None

        return {
            "strategy": self.strategy.value,
            "horizon": self.horizon.value,
            "horizon_months": self.horizon_months,
            "capital_deployed": s(self.capital_deployed),
            "profit": s(self.profit),
            "return_on_capital": s(self.return_on_capital),
            "capital_velocity": s(self.capital_velocity),
            "annualized_return_on_capital": s(self.annualized_return_on_capital),
            "profit_per_1k_deployed": s(self.profit_per_1k_deployed),
            "capital_recycled_percent": s(self.capital_recycled_percent),
            "share_of_available_capital": s(self.share_of_available_capital),
            "within_capital_limit": self.within_capital_limit,
            "capital_ceiling": s(self.capital_ceiling),
            "capital_free": self.capital_free,
            "computable": self.computable,
            "score": s(self.score),
            "score_target": s(self.score_target),
            "formula": self.formula,
            "notes": list(self.notes),
            "inputs": dict(self.inputs),
            "confidence": self.confidence.value,
            "provisional": True,
        }


def _target_return(
    profile: Optional[InvestorProfile], fallback: Optional[Numeric]
) -> Decimal:
    """The return this metric is scored against, in priority order."""
    if profile is not None and profile.minimum_roi is not None:
        return D(profile.minimum_roi)
    if fallback is not None:
        return D(fallback)
    return PROVISIONAL_TARGET_RETURN


def _score_from_return(
    annualized: Optional[Decimal], target: Decimal
) -> Optional[Decimal]:
    """Map an annualised return on capital onto 0-100. Deterministic."""
    if annualized is None or target <= 0:
        return None
    if annualized <= 0:
        return ZERO
    scaled = annualized / target * SCORE_AT_TARGET
    return ratio(min(scaled, SCORE_AT_TARGET * CAP_MULTIPLE))


def compute_capital_efficiency(
    result: StrategyResult,
    profile: Optional[InvestorProfile] = None,
    target_return: Optional[Numeric] = None,
) -> CapitalEfficiency:
    """Compute the capital efficiency of one strategy result.

    ``target_return`` is the fallback benchmark when the investor has not
    stated a minimum ROI — normally the deal's own flip ROI target.
    """
    strategy = result.strategy
    horizon = HORIZON_BY_STRATEGY[strategy]
    target = _target_return(profile, target_return)
    notes: List[str] = []

    capital = result.cash_required
    profit = result.profit

    # How long the capital is committed before the profit is measured.
    if horizon == ProfitHorizon.TRANSACTIONAL:
        horizon_months = result.time_to_liquidity_months
    else:
        horizon_months = 12

    inputs: Dict[str, Optional[str]] = {
        "capital_deployed": str(capital) if capital is not None else None,
        "profit": str(profit) if profit is not None else None,
        "horizon_months": str(horizon_months) if horizon_months is not None else None,
        "profit_horizon": horizon.value,
        "target_return": str(target),
        "target_return_source": (
            "investor profile"
            if profile is not None and profile.minimum_roi is not None
            else ("deal assumptions" if target_return is not None else "Atlas default")
        ),
    }

    if not result.viable or profit is None or capital is None:
        notes.append(
            "Capital efficiency cannot be computed: this strategy has no profit or "
            "capital figure."
        )
        return CapitalEfficiency(
            strategy=strategy,
            horizon=horizon,
            horizon_months=horizon_months,
            capital_deployed=capital,
            profit=profit,
            return_on_capital=None,
            capital_velocity=None,
            annualized_return_on_capital=None,
            profit_per_1k_deployed=None,
            capital_recycled_percent=_recycled_percent(result),
            share_of_available_capital=None,
            within_capital_limit=None,
            capital_ceiling=profile.capital_ceiling if profile else None,
            capital_free=False,
            computable=False,
            score=None,
            score_target=target,
            formula="Not computed — the strategy did not produce a profit and capital figure.",
            notes=notes,
            inputs=inputs,
            confidence=result.confidence,
        )

    capital_free = capital <= 0
    return_on_capital: Optional[Decimal] = None
    velocity: Optional[Decimal] = None
    annualized: Optional[Decimal] = None
    per_1k: Optional[Decimal] = None

    # How many times a year this capital could turn over. Income strategies keep
    # the capital committed, so it turns over once.
    if horizon == ProfitHorizon.TRANSACTIONAL and horizon_months and horizon_months > 0:
        velocity = ratio(MONTHS_PER_YEAR / D(horizon_months))
    elif horizon == ProfitHorizon.ANNUAL_INCOME:
        velocity = D("1.0000")

    if capital_free:
        if profit > 0:
            notes.append(
                "This strategy commits no capital, so return on capital is undefined "
                "rather than infinite. It scores full marks on efficiency because "
                "there is no capital to be inefficient with."
            )
        else:
            notes.append("No capital is committed and no profit is produced.")
    else:
        raw = safe_div(profit, capital)
        return_on_capital = ratio(raw) if raw is not None else None
        per_1k = money(profit / (capital / D("1000")))
        if return_on_capital is not None and velocity is not None:
            annualized = ratio(return_on_capital * velocity)

    if (
        horizon == ProfitHorizon.TRANSACTIONAL
        and velocity is not None
        and velocity > 1
    ):
        notes.append(
            f"Annualised at {velocity}x assumes the capital is redeployed into a "
            "comparable deal as soon as this one exits. If deal flow does not "
            "support that, the realised annual return is lower."
        )

    # Score: capital-free-and-profitable is the best possible use of capital.
    if capital_free:
        score = D("100.0000") if profit > 0 else ZERO
    else:
        score = _score_from_return(annualized, target)

    # Affordability, kept separate from efficiency.
    share: Optional[Decimal] = None
    within_limit: Optional[bool] = None
    ceiling = profile.capital_ceiling if profile else None
    if profile is not None and profile.available_capital is not None:
        divided = safe_div(capital, profile.available_capital)
        share = ratio(divided) if divided is not None else None
    if ceiling is not None:
        within_limit = capital <= ceiling
        if not within_limit:
            notes.append(
                f"Requires ${capital:,.0f} against a stated ceiling of ${ceiling:,.0f}. "
                "This is a funding constraint, not an efficiency problem — the return "
                "stands, the investor simply cannot cover it today."
            )

    recycled = _recycled_percent(result)
    if recycled is not None:
        notes.append(
            f"{recycled * 100:.0f}% of the capital put in is returned at refinance."
        )

    formula = _describe(horizon, capital_free, velocity, target)

    return CapitalEfficiency(
        strategy=strategy,
        horizon=horizon,
        horizon_months=horizon_months,
        capital_deployed=capital,
        profit=profit,
        return_on_capital=return_on_capital,
        capital_velocity=velocity,
        annualized_return_on_capital=annualized,
        profit_per_1k_deployed=per_1k,
        capital_recycled_percent=recycled,
        share_of_available_capital=share,
        within_capital_limit=within_limit,
        capital_ceiling=ceiling,
        capital_free=capital_free,
        computable=True,
        score=score,
        score_target=target,
        formula=formula,
        notes=notes,
        inputs=inputs,
        # The metric inherits the confidence of the numbers it is built from.
        confidence=result.confidence,
    )


def _recycled_percent(result: StrategyResult) -> Optional[Decimal]:
    """Share of invested capital returned at refinance (BRRRR only)."""
    detail = result.detail or {}
    invested = detail.get("cash_invested")
    returned = detail.get("cash_returned")
    if invested is None or returned is None:
        return None
    invested_dec = D(invested)
    if invested_dec <= 0:
        return None
    share = D(returned) / invested_dec
    return ratio(max(min(share, D("1")), ZERO))


def _describe(
    horizon: ProfitHorizon,
    capital_free: bool,
    velocity: Optional[Decimal],
    target: Decimal,
) -> str:
    """State exactly how the score was produced, so it can be checked by hand."""
    if capital_free:
        return (
            "No capital is committed, so return on capital is undefined. A "
            "profitable strategy that needs no capital scores 100."
        )
    if horizon == ProfitHorizon.ANNUAL_INCOME:
        return (
            "annual cash flow / capital deployed = annualised return on capital. "
            f"Scored against a {target * 100:.0f}% target, where hitting the target "
            "scores 50 and twice the target scores 100."
        )
    return (
        "profit / capital deployed x (12 / holding months) = annualised return on "
        f"capital. Scored against a {target * 100:.0f}% target, where hitting the "
        "target scores 50 and twice the target scores 100."
    )


def compute_all_capital_efficiency(
    results: Dict[Strategy, StrategyResult],
    profile: Optional[InvestorProfile] = None,
    target_return: Optional[Numeric] = None,
) -> Dict[Strategy, CapitalEfficiency]:
    """Compute the metric for every strategy in a comparison."""
    return {
        strategy: compute_capital_efficiency(result, profile, target_return)
        for strategy, result in results.items()
    }
