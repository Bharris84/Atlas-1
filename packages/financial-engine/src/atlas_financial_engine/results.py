"""Common result shape shared by every strategy model.

Each strategy computes different things, but the strategy engine has to compare
them on a level playing field. ``StrategyResult`` is that level playing field:
the handful of dimensions every strategy can be judged on, plus a ``detail``
payload carrying the strategy-specific breakdown.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from .enums import Confidence, Strategy
from .money import D, Numeric


def _s(value: Optional[Decimal]) -> Optional[str]:
    return str(value) if value is not None else None


@dataclass(frozen=True)
class Criterion:
    """One buy-box test and whether this deal passes it."""

    name: str
    label: str
    target: Optional[Decimal]
    actual: Optional[Decimal]
    met: bool
    unit: str = "currency"  # currency | percent | ratio | months

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "target": _s(self.target),
            "actual": _s(self.actual),
            "met": self.met,
            "unit": self.unit,
        }


@dataclass(frozen=True)
class StrategyResult:
    strategy: Strategy
    viable: bool
    # Total profit realised at exit (flip/wholesale) or over the modelled
    # horizon (rental strategies report annual cash flow instead).
    profit: Optional[Decimal] = None
    cash_required: Optional[Decimal] = None
    roi: Optional[Decimal] = None
    annualized_roi: Optional[Decimal] = None
    monthly_cash_flow: Optional[Decimal] = None
    annual_cash_flow: Optional[Decimal] = None
    equity_created: Optional[Decimal] = None
    dscr: Optional[Decimal] = None
    cap_rate: Optional[Decimal] = None
    cash_on_cash: Optional[Decimal] = None
    max_purchase_price: Optional[Decimal] = None
    time_to_liquidity_months: Optional[int] = None
    meets_criteria: bool = False
    criteria: List[Criterion] = field(default_factory=list)
    confidence: Confidence = Confidence.LOW
    confidence_reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    missing_inputs: List[str] = field(default_factory=list)
    not_viable_reason: Optional[str] = None
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "viable": self.viable,
            "profit": _s(self.profit),
            "cash_required": _s(self.cash_required),
            "roi": _s(self.roi),
            "annualized_roi": _s(self.annualized_roi),
            "monthly_cash_flow": _s(self.monthly_cash_flow),
            "annual_cash_flow": _s(self.annual_cash_flow),
            "equity_created": _s(self.equity_created),
            "dscr": _s(self.dscr),
            "cap_rate": _s(self.cap_rate),
            "cash_on_cash": _s(self.cash_on_cash),
            "max_purchase_price": _s(self.max_purchase_price),
            "time_to_liquidity_months": self.time_to_liquidity_months,
            "meets_criteria": self.meets_criteria,
            "criteria": [c.to_dict() for c in self.criteria],
            "confidence": self.confidence.value,
            "confidence_reasons": list(self.confidence_reasons),
            "warnings": list(self.warnings),
            "missing_inputs": list(self.missing_inputs),
            "not_viable_reason": self.not_viable_reason,
            "detail": self.detail,
        }


def not_viable(
    strategy: Strategy,
    reason: str,
    missing_inputs: Optional[List[str]] = None,
) -> StrategyResult:
    """A strategy that cannot be evaluated. Never silently returns zeros."""
    return StrategyResult(
        strategy=strategy,
        viable=False,
        not_viable_reason=reason,
        missing_inputs=list(missing_inputs or []),
        confidence=Confidence.LOW,
    )


def criterion(
    name: str,
    label: str,
    target: Optional[Numeric],
    actual: Optional[Numeric],
    *,
    unit: str = "currency",
    higher_is_better: bool = True,
) -> Criterion:
    """Build a criterion, treating an unknown actual as "not met"."""
    t = D(target) if target is not None else None
    a = D(actual) if actual is not None else None
    if a is None or t is None:
        met = False
    elif higher_is_better:
        met = a >= t
    else:
        met = a <= t
    return Criterion(name=name, label=label, target=t, actual=a, met=met, unit=unit)
