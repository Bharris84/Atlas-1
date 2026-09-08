"""Underwriting assumptions — the Atlas "buy box".

Everything in this module is a PROVISIONAL DEFAULT. None of these numbers are
laws of real estate; they are starting points chosen so the engine produces a
result before a user has tuned anything. Every field is overridable per deal,
and the API records an audit-trail entry whenever one changes.

``PROVISIONAL_DEFAULTS_NOTE`` is surfaced in the UI next to any value the user
has not explicitly overridden.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict, fields, is_dataclass, replace
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Union, get_args, get_origin, get_type_hints

from .enums import FinancingMethod
from .money import D, Numeric

PROVISIONAL_DEFAULTS_NOTE = (
    "Provisional underwriting default. Not a market-verified figure. "
    "Review and override before making an offer."
)


def _dec(value: Numeric) -> Decimal:
    return D(value)


@dataclass(frozen=True)
class TransactionCosts:
    """Costs of getting in and out of a property."""

    # Acquisition
    purchase_closing_percent: Decimal = D("0.02")  # title, escrow, recording, lender-agnostic
    purchase_closing_flat: Decimal = D("0")

    # Disposition
    sale_commission_percent: Decimal = D("0.06")
    sale_closing_percent: Decimal = D("0.02")  # seller-paid title/transfer/concessions
    sale_closing_flat: Decimal = D("0")

    # Catch-all
    miscellaneous_costs: Decimal = D("0")

    @property
    def total_sale_percent(self) -> Decimal:
        return self.sale_commission_percent + self.sale_closing_percent


@dataclass(frozen=True)
class HoldingCosts:
    """Monthly carrying costs while a property is owned but not producing income.

    Taxes and insurance are entered ANNUALLY because that is how they are
    quoted; everything else is monthly.
    """

    annual_taxes: Decimal = D("0")
    annual_insurance: Decimal = D("0")
    monthly_hoa: Decimal = D("0")
    monthly_utilities: Decimal = D("150")
    monthly_other: Decimal = D("0")

    @property
    def monthly_total(self) -> Decimal:
        return (
            self.annual_taxes / D("12")
            + self.annual_insurance / D("12")
            + self.monthly_hoa
            + self.monthly_utilities
            + self.monthly_other
        )


@dataclass(frozen=True)
class FinancingTerms:
    """A single financing package.

    ``loan_to_purchase`` and ``loan_to_rehab`` are fractions of purchase price
    and rehab budget respectively. Hard money lenders typically quote e.g.
    90% of purchase / 100% of rehab; conventional lenders quote a down payment,
    which is expressed here as ``loan_to_purchase = 1 - down_payment``.
    """

    method: FinancingMethod = FinancingMethod.HARD_MONEY
    loan_to_purchase: Decimal = D("0.90")
    loan_to_rehab: Decimal = D("1.00")
    annual_interest_rate: Decimal = D("0.11")
    points: Decimal = D("0.02")  # fraction of loan amount, paid at closing
    lender_fees_flat: Decimal = D("1500")
    interest_only: bool = True
    amortization_years: int = 30
    # Fraction of the rehab draw outstanding on average over the hold. Hard
    # money rehab draws fund progressively, so charging full interest on the
    # entire rehab loan for the whole hold overstates cost.
    average_rehab_draw_factor: Decimal = D("0.60")

    @property
    def down_payment_percent(self) -> Decimal:
        return D("1") - self.loan_to_purchase

    @property
    def is_cash(self) -> bool:
        return self.method == FinancingMethod.CASH or (
            self.loan_to_purchase == 0 and self.loan_to_rehab == 0
        )


CASH_PURCHASE = FinancingTerms(
    method=FinancingMethod.CASH,
    loan_to_purchase=D("0"),
    loan_to_rehab=D("0"),
    annual_interest_rate=D("0"),
    points=D("0"),
    lender_fees_flat=D("0"),
)

DEFAULT_HARD_MONEY = FinancingTerms()

DEFAULT_CONVENTIONAL = FinancingTerms(
    method=FinancingMethod.CONVENTIONAL,
    loan_to_purchase=D("0.75"),  # 25% down on an investment property
    loan_to_rehab=D("0"),
    annual_interest_rate=D("0.07"),
    points=D("0.01"),
    lender_fees_flat=D("1200"),
    interest_only=False,
    amortization_years=30,
)


@dataclass(frozen=True)
class WholesaleAssumptions:
    """Wholesale is underwritten from the END BUYER's deal, not a 70% rule."""

    target_assignment_fee: Decimal = D("10000")
    buyer_profit_percent_of_arv: Decimal = D("0.15")
    buyer_profit_floor: Decimal = D("20000")
    # Cushion held back so a buyer's own inspection doesn't kill the deal.
    risk_buffer_percent_of_arv: Decimal = D("0.02")
    risk_buffer_flat: Decimal = D("0")
    # Marketing / transactional funding / double-close costs borne by us.
    wholesale_transaction_costs: Decimal = D("0")
    # The rehab contingency the end buyer will apply to our scope.
    buyer_rehab_contingency: Decimal = D("0.15")
    buyer_holding_months: int = 6
    buyer_financing: FinancingTerms = field(default_factory=lambda: DEFAULT_HARD_MONEY)


@dataclass(frozen=True)
class FlipAssumptions:
    minimum_net_profit: Decimal = D("30000")
    minimum_roi: Decimal = D("0.20")
    rehab_contingency: Decimal = D("0.15")
    holding_months: int = 6
    financing: FinancingTerms = field(default_factory=lambda: DEFAULT_HARD_MONEY)


@dataclass(frozen=True)
class RentalAssumptions:
    vacancy_percent: Decimal = D("0.05")
    management_percent: Decimal = D("0.08")  # of collected rent
    maintenance_percent: Decimal = D("0.05")  # of gross scheduled rent
    capex_percent: Decimal = D("0.05")  # of gross scheduled rent
    annual_taxes: Decimal = D("0")
    annual_insurance: Decimal = D("0")
    monthly_hoa: Decimal = D("0")
    annual_other_expenses: Decimal = D("0")

    minimum_monthly_cash_flow: Decimal = D("300")
    minimum_cash_on_cash: Decimal = D("0.08")
    target_dscr: Decimal = D("1.25")

    financing: FinancingTerms = field(default_factory=lambda: DEFAULT_CONVENTIONAL)


@dataclass(frozen=True)
class BrrrrAssumptions:
    refinance_ltv: Decimal = D("0.75")
    max_cash_left_in_deal: Decimal = D("25000")
    minimum_equity_percent: Decimal = D("0.20")
    refinance_closing_percent: Decimal = D("0.02")  # of the new loan
    refinance_closing_flat: Decimal = D("0")
    seasoning_months: int = 6  # hold before the refi is available
    rehab_contingency: Decimal = D("0.15")
    acquisition_financing: FinancingTerms = field(default_factory=lambda: DEFAULT_HARD_MONEY)
    refinance_rate: Decimal = D("0.075")
    refinance_amortization_years: int = 30


@dataclass(frozen=True)
class SellerFinanceAssumptions:
    down_payment_percent: Decimal = D("0.10")
    annual_interest_rate: Decimal = D("0.06")
    amortization_years: int = 30
    balloon_years: Optional[int] = 5
    closing_costs_percent: Decimal = D("0.01")


@dataclass(frozen=True)
class StrategyRankingWeights:
    """How the strategy engine trades off competing goods.

    Capital efficiency is weighted heavily on purpose: early-stage, the binding
    constraint is cash, not opportunity.
    """

    profit: Decimal = D("0.25")
    capital_efficiency: Decimal = D("0.25")
    roi: Decimal = D("0.15")
    cash_flow: Decimal = D("0.10")
    equity_creation: Decimal = D("0.10")
    time_to_liquidity: Decimal = D("0.05")
    risk: Decimal = D("0.10")


@dataclass(frozen=True)
class Assumptions:
    """The complete assumption set for one analysis."""

    transaction: TransactionCosts = field(default_factory=TransactionCosts)
    holding: HoldingCosts = field(default_factory=HoldingCosts)
    wholesale: WholesaleAssumptions = field(default_factory=WholesaleAssumptions)
    flip: FlipAssumptions = field(default_factory=FlipAssumptions)
    rental: RentalAssumptions = field(default_factory=RentalAssumptions)
    brrrr: BrrrrAssumptions = field(default_factory=BrrrrAssumptions)
    seller_finance: SellerFinanceAssumptions = field(default_factory=SellerFinanceAssumptions)
    ranking: StrategyRankingWeights = field(default_factory=StrategyRankingWeights)

    def to_dict(self) -> Dict[str, Any]:
        return _serialize(asdict(self))

    @classmethod
    def from_dict(cls, data: Optional[Mapping[str, Any]]) -> "Assumptions":
        """Build an assumption set from a (possibly partial) mapping.

        Unknown keys are ignored rather than raising, so a stored analysis from
        an older schema still loads. Missing keys fall back to defaults.
        """
        if not data:
            return cls()
        return _build(cls, data)


def _serialize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    if hasattr(value, "value") and hasattr(value, "name"):  # Enum
        return value.value
    return value


def _build(cls: type, data: Mapping[str, Any]) -> Any:
    """Reconstruct a frozen assumption dataclass from a plain mapping.

    Types are resolved with ``get_type_hints`` rather than read off
    ``field.type``: this module uses postponed annotation evaluation, so
    ``field.type`` is the string ``"TransactionCosts"``, not the class. Reading
    it directly silently stores nested assumptions as raw dicts, which then
    fail at attribute access time — long after the analysis was saved.
    """
    hints = get_type_hints(cls)
    kwargs: Dict[str, Any] = {}
    for f in fields(cls):
        if f.name not in data:
            continue
        raw = data[f.name]
        ftype = hints.get(f.name, Any)

        if get_origin(ftype) is Union:  # Optional[X]
            if raw is None:
                kwargs[f.name] = None
                continue
            candidates = [t for t in get_args(ftype) if t is not type(None)]
            ftype = candidates[0] if candidates else Any
        elif raw is None:
            continue

        if is_dataclass(ftype):
            kwargs[f.name] = _build(ftype, raw)
        elif isinstance(ftype, type) and issubclass(ftype, Enum):
            kwargs[f.name] = ftype(raw)
        elif ftype is Decimal:
            kwargs[f.name] = D(raw)
        elif ftype is bool:
            kwargs[f.name] = bool(raw)
        elif ftype is int:
            kwargs[f.name] = int(raw)
        else:
            kwargs[f.name] = raw
    return cls(**kwargs)


def override(base: Any, **changes: Any) -> Any:
    """Type-preserving override helper for frozen assumption dataclasses."""
    return replace(base, **changes)
