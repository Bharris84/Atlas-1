"""Investor profile.

Deliberately separate from ``assumptions.py``, because the two answer different
questions:

* ``Assumptions`` describe **the deal** — what a rehab costs, what a lender
  charges, what an end buyer needs. Change the property and they change.
* ``InvestorProfile`` describes **the investor** — how much capital exists, how
  much of it may be committed, what returns are acceptable, how much risk is
  tolerable. It is the same across every property the investor looks at.

Conflating them is how underwriting tools end up unable to answer "can I
actually do this deal?" — a deal can be excellent and still be impossible for
an investor with $40,000 to their name.

Scope note (V0.1 calibration phase): this module defines the profile and lets
the capital efficiency metric read it. It deliberately does NOT yet influence
strategy ranking or the deal score. That wiring is a later decision, and it
should be made against calibration evidence rather than guesswork.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, is_dataclass, replace
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Union, get_args, get_origin, get_type_hints

from .enums import Strategy
from .money import D, Numeric

PROVISIONAL_PROFILE_NOTE = (
    "Provisional investor profile. These figures describe the investor, not the "
    "property, and nothing in Atlas has validated them. Review before relying on "
    "any capital-constraint conclusion."
)


class RiskTolerance(str, Enum):
    """How much execution and estimate risk the investor will accept.

    Ordered, so comparisons are meaningful.
    """

    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"

    @property
    def rank(self) -> int:
        return {"conservative": 0, "moderate": 1, "aggressive": 2}[self.value]


class CapitalEfficiencyPreference(str, Enum):
    """How the investor trades absolute profit against capital turnover.

    An investor with little capital usually wants it back quickly, even at a
    lower profit per deal. An investor with plenty usually wants the larger
    absolute number. This records which one applies.
    """

    MAXIMIZE_VELOCITY = "maximize_velocity"
    BALANCED = "balanced"
    MAXIMIZE_ABSOLUTE_PROFIT = "maximize_absolute_profit"


@dataclass(frozen=True)
class InvestorProfile:
    """Capital constraints and return requirements for one investor.

    Every field is optional. An investor who has not stated their available
    capital is not an investor with zero capital, and the metrics that depend on
    it report "unknown" rather than assuming a number.
    """

    name: Optional[str] = None

    # --- Capital ------------------------------------------------------------
    available_capital: Optional[Decimal] = None
    # The most the investor is willing to put into a SINGLE deal. Usually well
    # below available capital, because committing everything to one property
    # ends the business if it goes wrong.
    max_capital_deployment: Optional[Decimal] = None

    # --- Return requirements -----------------------------------------------
    preferred_minimum_cash_flow: Optional[Decimal] = None  # monthly
    minimum_roi: Optional[Decimal] = None  # fraction, e.g. 0.20
    max_cash_left_in_deal: Optional[Decimal] = None
    minimum_wholesale_assignment: Optional[Decimal] = None

    # --- Preferences --------------------------------------------------------
    risk_tolerance: RiskTolerance = RiskTolerance.MODERATE
    capital_efficiency_preference: CapitalEfficiencyPreference = (
        CapitalEfficiencyPreference.BALANCED
    )
    # Empty means no stated preference — which is different from "no strategy is
    # acceptable", and is treated as "all of them".
    preferred_strategies: List[Strategy] = field(default_factory=list)

    def prefers(self, strategy: Strategy) -> bool:
        """True when a strategy is acceptable to this investor."""
        return not self.preferred_strategies or strategy in self.preferred_strategies

    @property
    def is_stated(self) -> bool:
        """True when the investor has supplied anything at all."""
        return any(
            value is not None
            for value in (
                self.available_capital,
                self.max_capital_deployment,
                self.preferred_minimum_cash_flow,
                self.minimum_roi,
                self.max_cash_left_in_deal,
                self.minimum_wholesale_assignment,
            )
        ) or bool(self.preferred_strategies)

    @property
    def capital_ceiling(self) -> Optional[Decimal]:
        """The most that may go into one deal.

        The binding constraint is whichever is lower: what the investor has, or
        what they are willing to commit to a single property.
        """
        limits = [
            limit
            for limit in (self.available_capital, self.max_capital_deployment)
            if limit is not None
        ]
        return min(limits) if limits else None

    def to_dict(self) -> Dict[str, Any]:
        return _serialize(asdict(self))

    @classmethod
    def from_dict(cls, data: Optional[Mapping[str, Any]]) -> "InvestorProfile":
        """Build a profile from a partial mapping, ignoring unknown keys."""
        if not data:
            return cls()
        hints = get_type_hints(cls)
        kwargs: Dict[str, Any] = {}
        for f in fields(cls):
            if f.name not in data:
                continue
            raw = data[f.name]
            ftype = hints.get(f.name, Any)

            if f.name == "preferred_strategies":
                kwargs[f.name] = [Strategy(item) for item in (raw or [])]
                continue

            if get_origin(ftype) is Union:  # Optional[X]
                if raw is None or raw == "":
                    kwargs[f.name] = None
                    continue
                candidates = [t for t in get_args(ftype) if t is not type(None)]
                ftype = candidates[0] if candidates else Any
            elif raw is None:
                continue

            if isinstance(ftype, type) and issubclass(ftype, Enum):
                kwargs[f.name] = ftype(raw)
            elif ftype is Decimal:
                kwargs[f.name] = D(raw)
            else:
                kwargs[f.name] = raw
        return cls(**kwargs)

    def override(self, **changes: Any) -> "InvestorProfile":
        return replace(self, **changes)


def _serialize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    return value


# A starting point for an early-stage, capital-constrained operator: enough
# capital to wholesale and to take one modest flip, not enough to hold much.
# Provisional. Replace with the investor's real figures.
EARLY_STAGE_PROFILE = InvestorProfile(
    name="Early stage (provisional)",
    available_capital=D("50000"),
    max_capital_deployment=D("35000"),
    preferred_minimum_cash_flow=D("300"),
    minimum_roi=D("0.20"),
    max_cash_left_in_deal=D("25000"),
    minimum_wholesale_assignment=D("10000"),
    risk_tolerance=RiskTolerance.MODERATE,
    capital_efficiency_preference=CapitalEfficiencyPreference.MAXIMIZE_VELOCITY,
    preferred_strategies=[],
)
