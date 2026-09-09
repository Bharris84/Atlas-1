"""Calibration — comparing what Atlas predicted against what actually happened.

The engine's arithmetic is correct and tested. That is a different claim from
"the engine's answers are right", because an answer is only as good as the
assumptions behind it. A 15% rehab contingency and a 6% commission are
provisional guesses until real deals say otherwise.

This module measures that gap deterministically. No machine learning, no
fitting, no hidden adjustment: it re-runs the engine with known actual values
substituted in, one at a time, and reports how far each substitution moves the
predicted profit. That isolates which assumption was wrong.

Two numbers matter most in the output:

* **Attribution** — how much of the gap each individual input explains. Answers
  "was it my ARV or my rehab that was off?"
* **Unexplained residual** — what remains after EVERY known actual has been
  substituted. This is the part the inputs cannot explain, which means the cost
  model itself is wrong. A residual that is consistently negative across deals
  says Atlas is systematically missing a real cost.

Nothing here writes back into the engine. Calibration reports; a human decides
what to change.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from .assumptions import Assumptions
from .capital_efficiency import HORIZON_BY_STRATEGY, ProfitHorizon
from .enums import Strategy
from .inputs import DealInputs
from .money import D, Numeric, ZERO, money, ratio, safe_div
from .results import StrategyResult
from .strategies.brrrr import analyze_brrrr
from .strategies.buy_hold import analyze_buy_hold
from .strategies.flip import analyze_flip
from .strategies.seller_finance import analyze_seller_finance
from .strategies.wholesale import analyze_wholesale

ANALYZERS: Dict[Strategy, Callable[[DealInputs], StrategyResult]] = {
    Strategy.WHOLESALE: analyze_wholesale,
    Strategy.FLIP: analyze_flip,
    Strategy.BUY_HOLD: analyze_buy_hold,
    Strategy.BRRRR: analyze_brrrr,
    Strategy.SELLER_FINANCE: analyze_seller_finance,
}

PROFIT_BASIS = {
    ProfitHorizon.TRANSACTIONAL: (
        "net profit realised at exit"
    ),
    ProfitHorizon.ANNUAL_INCOME: (
        "annual cash flow (not a one-off exit profit)"
    ),
}


@dataclass(frozen=True)
class ActualOutcome:
    """What really happened. Every field optional except the realised profit.

    ``actual_profit`` must be stated on the same basis as the executed
    strategy's profit — an exit profit for a wholesale or flip, an annual cash
    flow for a hold. ``profit_basis`` on the result says which applies.
    """

    strategy_executed: Strategy
    actual_profit: Decimal

    actual_purchase_price: Optional[Decimal] = None
    actual_sale_price: Optional[Decimal] = None  # the ARV that materialised
    actual_rehab: Optional[Decimal] = None
    actual_monthly_rent: Optional[Decimal] = None
    actual_holding_months: Optional[int] = None
    notes: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ActualOutcome":
        def opt(key: str) -> Optional[Decimal]:
            value = data.get(key)
            return D(value) if value not in (None, "") else None

        return cls(
            strategy_executed=Strategy(data["strategy_executed"]),
            actual_profit=D(data["actual_profit"]),
            actual_purchase_price=opt("actual_purchase_price"),
            actual_sale_price=opt("actual_sale_price"),
            actual_rehab=opt("actual_rehab"),
            actual_monthly_rent=opt("actual_monthly_rent"),
            actual_holding_months=(
                int(data["actual_holding_months"])
                if data.get("actual_holding_months") is not None
                else None
            ),
            notes=data.get("notes"),
        )


@dataclass(frozen=True)
class Attribution:
    """How much one wrong input moved the predicted profit."""

    factor: str
    label: str
    predicted_value: Optional[str]
    actual_value: Optional[str]
    profit_impact: Decimal
    share_of_gap: Optional[Decimal]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "factor": self.factor,
            "label": self.label,
            "predicted_value": self.predicted_value,
            "actual_value": self.actual_value,
            "profit_impact": str(self.profit_impact),
            "share_of_gap": str(self.share_of_gap) if self.share_of_gap is not None else None,
        }


@dataclass(frozen=True)
class CalibrationResult:
    name: str
    strategy: Strategy
    profit_basis: str

    predicted_profit: Optional[Decimal]
    actual_profit: Decimal
    difference: Optional[Decimal]
    difference_percent: Optional[Decimal]

    # Predicted profit re-run with every known actual substituted in.
    profit_with_actual_inputs: Optional[Decimal]
    # How much of the gap the wrong inputs account for.
    explained_by_inputs: Optional[Decimal]
    # What is left once the inputs are corrected: cost-model error.
    unexplained_residual: Optional[Decimal]
    # One-at-a-time impacts do not sum exactly when factors interact.
    interaction_effect: Optional[Decimal]

    attributions: List[Attribution] = field(default_factory=list)
    dominant_factor: Optional[str] = None
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        def s(v: Optional[Decimal]) -> Optional[str]:
            return str(v) if v is not None else None

        return {
            "name": self.name,
            "strategy": self.strategy.value,
            "profit_basis": self.profit_basis,
            "predicted_profit": s(self.predicted_profit),
            "actual_profit": s(self.actual_profit),
            "difference": s(self.difference),
            "difference_percent": s(self.difference_percent),
            "profit_with_actual_inputs": s(self.profit_with_actual_inputs),
            "explained_by_inputs": s(self.explained_by_inputs),
            "unexplained_residual": s(self.unexplained_residual),
            "interaction_effect": s(self.interaction_effect),
            "attributions": [a.to_dict() for a in self.attributions],
            "dominant_factor": self.dominant_factor,
            "notes": list(self.notes),
        }


# --- Substitutions ----------------------------------------------------------
#
# Each factor knows how to rewrite DealInputs so one predicted value is
# replaced by its actual. Adding a factor means adding one entry here.


def _sub_purchase_price(inputs: DealInputs, value: Decimal) -> DealInputs:
    return replace(inputs, purchase_price=value)


def _sub_arv(inputs: DealInputs, value: Decimal) -> DealInputs:
    # Clear the range too, or the midpoint would override the point estimate.
    return replace(inputs, arv=value, arv_low=None, arv_high=None)


def _sub_rehab(inputs: DealInputs, value: Decimal) -> DealInputs:
    return replace(inputs, rehab=value, rehab_low=None, rehab_high=None)


def _sub_rent(inputs: DealInputs, value: Decimal) -> DealInputs:
    return replace(inputs, monthly_rent=value)


def _sub_holding_months(inputs: DealInputs, value: Decimal, strategy: Strategy) -> DealInputs:
    """Holding period lives in a different assumption per strategy."""
    months = int(value)
    a = inputs.assumptions
    if strategy == Strategy.BRRRR:
        return replace(inputs, assumptions=replace(a, brrrr=replace(a.brrrr, seasoning_months=months)))
    if strategy == Strategy.WHOLESALE:
        return replace(
            inputs,
            assumptions=replace(a, wholesale=replace(a.wholesale, buyer_holding_months=months)),
        )
    return replace(inputs, assumptions=replace(a, flip=replace(a.flip, holding_months=months)))


FACTORS: List[Tuple[str, str, str]] = [
    # (factor key, ActualOutcome field, human label)
    ("purchase_price", "actual_purchase_price", "Purchase price"),
    ("arv", "actual_sale_price", "ARV / sale price"),
    ("rehab", "actual_rehab", "Rehab"),
    ("monthly_rent", "actual_monthly_rent", "Monthly rent"),
    ("holding_months", "actual_holding_months", "Holding period"),
]


def _apply(inputs: DealInputs, factor: str, value: Decimal, strategy: Strategy) -> DealInputs:
    if factor == "purchase_price":
        return _sub_purchase_price(inputs, value)
    if factor == "arv":
        return _sub_arv(inputs, value)
    if factor == "rehab":
        return _sub_rehab(inputs, value)
    if factor == "monthly_rent":
        return _sub_rent(inputs, value)
    if factor == "holding_months":
        return _sub_holding_months(inputs, value, strategy)
    raise ValueError(f"unknown calibration factor: {factor}")


def _predicted_value(inputs: DealInputs, factor: str, strategy: Strategy) -> Optional[str]:
    if factor == "purchase_price":
        return str(inputs.purchase_price) if inputs.purchase_price is not None else None
    if factor == "arv":
        return str(inputs.effective_arv) if inputs.effective_arv is not None else None
    if factor == "rehab":
        return str(inputs.effective_rehab) if inputs.effective_rehab is not None else None
    if factor == "monthly_rent":
        return str(inputs.monthly_rent) if inputs.monthly_rent is not None else None
    if factor == "holding_months":
        a = inputs.assumptions
        if strategy == Strategy.BRRRR:
            return str(a.brrrr.seasoning_months)
        if strategy == Strategy.WHOLESALE:
            return str(a.wholesale.buyer_holding_months)
        return str(a.flip.holding_months)
    return None


def calibrate_deal(
    name: str, inputs: DealInputs, outcome: ActualOutcome
) -> CalibrationResult:
    """Compare one prediction against one known outcome."""
    strategy = outcome.strategy_executed
    analyze = ANALYZERS[strategy]
    horizon = HORIZON_BY_STRATEGY[strategy]
    notes: List[str] = []

    baseline = analyze(inputs)
    predicted = baseline.profit

    if not baseline.viable or predicted is None:
        notes.append(
            "Atlas could not underwrite this deal as entered, so there is no "
            f"prediction to compare: {baseline.not_viable_reason}"
        )
        return CalibrationResult(
            name=name,
            strategy=strategy,
            profit_basis=PROFIT_BASIS[horizon],
            predicted_profit=None,
            actual_profit=outcome.actual_profit,
            difference=None,
            difference_percent=None,
            profit_with_actual_inputs=None,
            explained_by_inputs=None,
            unexplained_residual=None,
            interaction_effect=None,
            notes=notes,
        )

    difference = money(outcome.actual_profit - predicted)
    pct = safe_div(difference, abs(predicted)) if predicted != 0 else None

    # One-at-a-time: swap a single input for its actual and see what moves.
    attributions: List[Attribution] = []
    all_actuals = inputs
    for factor, field_name, label in FACTORS:
        actual_value = getattr(outcome, field_name)
        if actual_value is None:
            continue
        value = D(actual_value)
        swapped = analyze(_apply(inputs, factor, value, strategy))
        if swapped.profit is None:
            continue
        impact = money(swapped.profit - predicted)
        attributions.append(
            Attribution(
                factor=factor,
                label=label,
                predicted_value=_predicted_value(inputs, factor, strategy),
                actual_value=str(value),
                profit_impact=impact,
                share_of_gap=(ratio(impact / difference) if difference != 0 else None),
            )
        )
        all_actuals = _apply(all_actuals, factor, value, strategy)

    with_actuals = analyze(all_actuals)
    profit_with_actuals = with_actuals.profit
    explained: Optional[Decimal] = None
    residual: Optional[Decimal] = None
    interaction: Optional[Decimal] = None

    if profit_with_actuals is not None:
        explained = money(profit_with_actuals - predicted)
        residual = money(outcome.actual_profit - profit_with_actuals)
        interaction = money(explained - sum((a.profit_impact for a in attributions), ZERO))

    dominant = None
    if attributions:
        dominant = max(attributions, key=lambda a: abs(a.profit_impact)).label

    if not attributions:
        notes.append(
            "No actual input values were supplied, so the gap cannot be attributed "
            "to any particular assumption."
        )
    if residual is not None and abs(residual) > D("1000"):
        notes.append(
            f"${abs(residual):,.0f} of the gap survives correcting every known input. "
            "That points at the cost model — a real cost Atlas is not charging, or "
            "one it overstates — rather than at a bad estimate."
        )
    if interaction is not None and abs(interaction) > D("500"):
        notes.append(
            f"${abs(interaction):,.0f} comes from factors interacting, so the "
            "individual attributions below do not sum to the total on their own."
        )

    return CalibrationResult(
        name=name,
        strategy=strategy,
        profit_basis=PROFIT_BASIS[horizon],
        predicted_profit=predicted,
        actual_profit=outcome.actual_profit,
        difference=difference,
        difference_percent=ratio(pct) if pct is not None else None,
        profit_with_actual_inputs=profit_with_actuals,
        explained_by_inputs=explained,
        unexplained_residual=residual,
        interaction_effect=interaction,
        attributions=sorted(attributions, key=lambda a: abs(a.profit_impact), reverse=True),
        dominant_factor=dominant,
        notes=notes,
    )


@dataclass(frozen=True)
class CalibrationReport:
    """Aggregate across several deals. Small samples say little — say so."""

    results: List[CalibrationResult]
    mean_absolute_error: Optional[Decimal]
    mean_signed_error: Optional[Decimal]
    mean_unexplained_residual: Optional[Decimal]
    factor_totals: Dict[str, Decimal]
    dominant_factor_counts: Dict[str, int]
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        def s(v: Optional[Decimal]) -> Optional[str]:
            return str(v) if v is not None else None

        return {
            "results": [r.to_dict() for r in self.results],
            "deal_count": len(self.results),
            "mean_absolute_error": s(self.mean_absolute_error),
            "mean_signed_error": s(self.mean_signed_error),
            "mean_unexplained_residual": s(self.mean_unexplained_residual),
            "factor_totals": {k: str(v) for k, v in self.factor_totals.items()},
            "dominant_factor_counts": dict(self.dominant_factor_counts),
            "notes": list(self.notes),
        }


def build_report(results: List[CalibrationResult]) -> CalibrationReport:
    """Summarise a set of calibration results."""
    comparable = [r for r in results if r.difference is not None]
    notes: List[str] = []

    mae = signed = residual_mean = None
    if comparable:
        count = D(len(comparable))
        mae = money(sum((abs(r.difference) for r in comparable), ZERO) / count)
        signed = money(sum((r.difference for r in comparable), ZERO) / count)
        residuals = [r.unexplained_residual for r in comparable if r.unexplained_residual is not None]
        if residuals:
            residual_mean = money(sum(residuals, ZERO) / D(len(residuals)))

    factor_totals: Dict[str, Decimal] = {}
    dominant_counts: Dict[str, int] = {}
    for result in comparable:
        for attribution in result.attributions:
            factor_totals[attribution.label] = money(
                factor_totals.get(attribution.label, ZERO) + abs(attribution.profit_impact)
            )
        if result.dominant_factor:
            dominant_counts[result.dominant_factor] = (
                dominant_counts.get(result.dominant_factor, 0) + 1
            )

    if len(comparable) < 3:
        notes.append(
            f"Only {len(comparable)} deal(s) compared. This is an illustration of the "
            "method, not evidence about the assumptions."
        )
    elif len(comparable) < 10:
        notes.append(
            f"{len(comparable)} deals is enough to spot a large systematic bias and "
            "nothing finer. Treat any single-factor conclusion as provisional."
        )

    if signed is not None and mae is not None and mae > 0:
        # A signed error close to the absolute error means the errors all point
        # the same way, which is bias rather than noise.
        consistency = abs(signed) / mae
        if consistency > D("0.7"):
            direction = "under" if signed > 0 else "over"
            notes.append(
                f"Errors are consistently in one direction: Atlas {direction}states "
                f"profit by ${abs(signed):,.0f} on average. That is a bias in the "
                "assumptions, not random variance."
            )

    if residual_mean is not None and abs(residual_mean) > D("1000"):
        direction = "understates" if residual_mean > 0 else "overstates"
        notes.append(
            f"Even with every known input corrected, Atlas {direction} profit by "
            f"${abs(residual_mean):,.0f} on average. Review the cost model before "
            "the estimates."
        )

    return CalibrationReport(
        results=results,
        mean_absolute_error=mae,
        mean_signed_error=signed,
        mean_unexplained_residual=residual_mean,
        factor_totals=factor_totals,
        dominant_factor_counts=dominant_counts,
        notes=notes,
    )


def calibrate_from_dicts(deals: List[Mapping[str, Any]]) -> CalibrationReport:
    """Run calibration over deals described as plain dictionaries.

    Each entry needs a ``name``, an ``inputs`` block in the shape
    ``DealInputs.from_dict`` accepts, and an ``actual`` block for
    ``ActualOutcome.from_dict``.
    """
    results = [
        calibrate_deal(
            name=deal.get("name", "Unnamed deal"),
            inputs=DealInputs.from_dict(deal["inputs"]),
            outcome=ActualOutcome.from_dict(deal["actual"]),
        )
        for deal in deals
    ]
    return build_report(results)
