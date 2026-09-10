"""Underwriting assumptions — the Atlas "buy box".

Everything in this module is a PROVISIONAL DEFAULT. None of these numbers are
laws of real estate; they are starting points chosen so the engine produces a
result before a user has tuned anything. Every field is overridable per deal,
and the API records an audit-trail entry whenever one changes.

``PROVISIONAL_DEFAULTS_NOTE`` is surfaced in the UI next to any value the user
has not explicitly overridden.

Operating expenses are the exception to "every field has a default". Taxes,
insurance, HOA and utilities are ``Optional`` and default to ``None``, because
there is no defensible default: they are property-specific facts, and the old
zero default silently claimed a property had no tax bill. See
``UNKNOWN_EXPENSE_NOTE``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict, fields, is_dataclass, replace
from decimal import Decimal
from enum import Enum
from typing import (
    Any,
    Dict,
    List,
    Mapping,
    Optional,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

from .enums import FinancingMethod
from .money import D, Numeric

PROVISIONAL_DEFAULTS_NOTE = (
    "Provisional underwriting default. Not a market-verified figure. "
    "Review and override before making an offer."
)


UNKNOWN_EXPENSE_NOTE = (
    "Not known. Atlas leaves this out of the arithmetic rather than guessing, "
    "so any figure derived from it is overstated until a real number is entered. "
    "Enter 0 explicitly if the expense genuinely does not apply."
)

# Expenses whose absence Atlas treats as blocking. Every property in the United
# States is taxed and every lender requires insurance, so a missing figure here
# is always an omission, never a real zero — and omitting them overstates cash
# flow by hundreds of dollars a month on a typical single-family rental.
#
# HOA and utilities are deliberately NOT on this list. Most properties have no
# HOA, and utilities on a rental are frequently tenant-paid, so an unknown is
# often a genuine zero. Atlas reports those as unknown but does not block on
# them; blocking every deal for a fee most properties do not have would train
# the user to ignore the flag.
BLOCKING_UNKNOWN_EXPENSES = ("annual_taxes", "annual_insurance")

# Bump when the meaning of a stored assumptions blob changes. Version 1 made
# operating expenses tri-state; before it, a stored ``0`` for taxes or
# insurance meant "nobody filled this in". ``Assumptions.from_dict`` reads a
# missing or ``0`` version as legacy and preserves that original meaning, so
# reloading an old analysis does not silently reinterpret it as a real zero.
ASSUMPTIONS_SCHEMA_VERSION = 1

_LEGACY_UNKNOWN_FIELDS = ("annual_taxes", "annual_insurance", "monthly_hoa")
# The pre-tri-state default for utilities: an invented number, but an
# intentional one. Legacy blobs keep it so their totals still reproduce.
_LEGACY_UTILITIES_DEFAULT = "150"


def _dec(value: Numeric) -> Decimal:
    return D(value)


def known(value: Optional[Decimal]) -> Decimal:
    """An unknown expense contributes nothing to the arithmetic.

    This is NOT the old zero default wearing a new name. The difference is that
    the omission is reported: anything calling this must also surface
    ``unknown_fields()`` so the resulting figure is labelled incomplete. Used
    on its own it would be exactly the bug this module was changed to fix.
    """
    return value if value is not None else D("0")


def _unknown_among(source: Any, names: tuple) -> List[str]:
    return [n for n in names if getattr(source, n) is None]


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

    The four property-specific expenses are tri-state: a number is a known
    figure, an explicit ``0`` means the expense does not apply, and ``None``
    means nobody has found out yet. ``monthly_other`` stays a plain zero — it
    is a catch-all for costs the user chooses to add, so "none added" is a
    genuine zero rather than an unanswered question.
    """

    annual_taxes: Optional[Decimal] = None
    annual_insurance: Optional[Decimal] = None
    monthly_hoa: Optional[Decimal] = None
    monthly_utilities: Optional[Decimal] = None
    monthly_other: Decimal = D("0")

    EXPENSE_FIELDS = ("annual_taxes", "annual_insurance", "monthly_hoa", "monthly_utilities")

    def unknown_fields(self) -> List[str]:
        """Expenses nobody has established yet, in display order."""
        return _unknown_among(self, self.EXPENSE_FIELDS)

    def blocking_unknowns(self) -> List[str]:
        return [n for n in self.unknown_fields() if n in BLOCKING_UNKNOWN_EXPENSES]

    @property
    def monthly_total(self) -> Decimal:
        """Carrying cost per month, with unknowns omitted.

        Omitting them UNDERSTATES the cost. That is the honest direction to be
        wrong in — a guessed figure would look like knowledge — but it is only
        acceptable because ``unknown_fields()`` is reported alongside it.
        """
        return (
            known(self.annual_taxes) / D("12")
            + known(self.annual_insurance) / D("12")
            + known(self.monthly_hoa)
            + known(self.monthly_utilities)
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
    # Tri-state, as on HoldingCosts: a figure, an explicit 0, or unknown.
    annual_taxes: Optional[Decimal] = None
    annual_insurance: Optional[Decimal] = None
    monthly_hoa: Optional[Decimal] = None
    annual_other_expenses: Decimal = D("0")

    minimum_monthly_cash_flow: Decimal = D("300")
    minimum_cash_on_cash: Decimal = D("0.08")
    target_dscr: Decimal = D("1.25")

    financing: FinancingTerms = field(default_factory=lambda: DEFAULT_CONVENTIONAL)

    EXPENSE_FIELDS = ("annual_taxes", "annual_insurance", "monthly_hoa")

    def unknown_fields(self) -> List[str]:
        return _unknown_among(self, self.EXPENSE_FIELDS)

    def blocking_unknowns(self) -> List[str]:
        return [n for n in self.unknown_fields() if n in BLOCKING_UNKNOWN_EXPENSES]


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

    # Which generation of assumption semantics this set was written under.
    # See ASSUMPTIONS_SCHEMA_VERSION.
    schema_version: int = ASSUMPTIONS_SCHEMA_VERSION

    def unknown_expenses(self) -> Dict[str, List[str]]:
        """Unknown operating expenses, grouped by the section they live in."""
        return {
            "holding": self.holding.unknown_fields(),
            "rental": self.rental.unknown_fields(),
        }

    def blocking_unknown_expenses(self) -> List[str]:
        """Dotted paths of the unknowns that must stop a PURSUE recommendation."""
        return [
            f"{section}.{name}"
            for section, source in (("holding", self.holding), ("rental", self.rental))
            for name in source.blocking_unknowns()
        ]

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
        return _build(cls, migrate_assumptions(data))


def migrate_assumptions(data: Mapping[str, Any]) -> Mapping[str, Any]:
    """Bring a stored assumptions blob up to the current schema version.

    A blob that does not declare ``schema_version`` is treated as legacy. That
    is deliberate: every blob written before version 1 lacks the key, and
    reading one as current would silently turn its zeros into real figures.
    A caller building a fresh assumption set by hand — a seed script, or an API
    client — must therefore declare the current version. Getting that wrong
    fails loudly (the values come back as unknown and the response says so),
    whereas the opposite default would fail silently.

    Only one migration exists so far, and it exists because the meaning of a
    stored value changed rather than its shape. Before version 1, taxes,
    insurance and HOA defaulted to ``0`` and that zero was how "nobody entered
    this" was represented. Reading such a blob today would turn every legacy
    analysis into a confident claim that the property has no tax bill — the
    analysis would not merely be stale, it would assert something false.

    So a legacy zero becomes ``None``, and utilities keep the invented ``150``
    they were actually computed with, because the point of a stored analysis is
    that it reproduces. A legacy blob that carried a NON-zero figure is
    untouched: that was a real number someone entered.
    """
    version = int(data.get("schema_version") or 0)
    if version >= ASSUMPTIONS_SCHEMA_VERSION:
        return data

    migrated = dict(data)
    for section in ("holding", "rental"):
        raw = migrated.get(section)
        if not isinstance(raw, Mapping):
            continue
        block = dict(raw)
        for name in _LEGACY_UNKNOWN_FIELDS:
            if name in block and block[name] is not None and D(block[name]) == 0:
                block[name] = None
        if section == "holding":
            block.setdefault("monthly_utilities", _LEGACY_UTILITIES_DEFAULT)
        migrated[section] = block
    # A legacy blob that omitted a section entirely still needs the utilities
    # figure it was computed with.
    migrated.setdefault("holding", {"monthly_utilities": _LEGACY_UTILITIES_DEFAULT})
    migrated["schema_version"] = ASSUMPTIONS_SCHEMA_VERSION
    return migrated


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
            # "" is what an emptied form field sends. It means the user cleared
            # the value, which is unknown — not zero.
            if raw is None or raw == "":
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
