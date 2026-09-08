"""The shared project cost model.

Wholesale, flip and BRRRR all price the same underlying question: what does it
cost to buy this property, fix it, carry it, and sell or refinance it? That
model lives here once so the three strategies cannot drift apart.

A second, important job of this module is exposing the cost model as a LINEAR
FUNCTION of purchase price. Costs like acquisition closing, loan points and
interest all scale with the price, so "what is the most I can pay and still
hit my target?" is a solvable equation rather than a search loop. Solving it
exactly keeps max-price answers reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional

from .assumptions import FinancingTerms, HoldingCosts, TransactionCosts
from .loans import monthly_rate, payment_factor
from .money import D, MONTHS_PER_YEAR, Numeric, ZERO, money


def interest_factor(
    annual_rate: Numeric,
    amortization_years: int,
    months: int,
    interest_only: bool,
) -> Decimal:
    """Interest paid per $1 borrowed over ``months``. Exact, unrounded.

    Interest is linear in principal for both interest-only and amortizing
    loans, which is what makes the max-price solver exact.
    """
    m = int(months)
    if m <= 0:
        return ZERO
    i = monthly_rate(annual_rate)
    if interest_only:
        return i * D(m)
    n = int(amortization_years) * 12
    m = min(m, n)
    if i == 0:
        return ZERO
    growth = (D(1) + i) ** n
    growth_m = (D(1) + i) ** m
    balance_per_dollar = (growth - growth_m) / (growth - D(1))
    return payment_factor(annual_rate, amortization_years) * D(m) - (D(1) - balance_per_dollar)


@dataclass(frozen=True)
class FinancingBreakdown:
    loan_amount: Decimal
    purchase_loan: Decimal
    rehab_loan: Decimal
    points_cost: Decimal
    interest_cost: Decimal
    lender_fees: Decimal
    total: Decimal

    def to_dict(self) -> Dict[str, Any]:
        return {
            "loan_amount": str(self.loan_amount),
            "purchase_loan": str(self.purchase_loan),
            "rehab_loan": str(self.rehab_loan),
            "points_cost": str(self.points_cost),
            "interest_cost": str(self.interest_cost),
            "lender_fees": str(self.lender_fees),
            "total": str(self.total),
        }


@dataclass(frozen=True)
class ProjectCosts:
    """Full cost stack for a buy/fix/exit project."""

    purchase_price: Decimal
    rehab_base: Decimal
    rehab_contingency_amount: Decimal
    rehab_total: Decimal
    acquisition_closing_costs: Decimal
    monthly_holding_costs: Decimal
    holding_months: int
    holding_costs: Decimal
    financing: FinancingBreakdown
    selling_costs: Decimal
    miscellaneous_costs: Decimal
    total_project_cost: Decimal
    total_basis: Decimal
    cash_required: Decimal

    def to_dict(self) -> Dict[str, Any]:
        return {
            "purchase_price": str(self.purchase_price),
            "rehab_base": str(self.rehab_base),
            "rehab_contingency_amount": str(self.rehab_contingency_amount),
            "rehab_total": str(self.rehab_total),
            "acquisition_closing_costs": str(self.acquisition_closing_costs),
            "monthly_holding_costs": str(self.monthly_holding_costs),
            "holding_months": self.holding_months,
            "holding_costs": str(self.holding_costs),
            "financing": self.financing.to_dict(),
            "financing_costs": str(self.financing.total),
            "selling_costs": str(self.selling_costs),
            "miscellaneous_costs": str(self.miscellaneous_costs),
            "total_project_cost": str(self.total_project_cost),
            "total_basis": str(self.total_basis),
            "cash_required": str(self.cash_required),
        }


def selling_costs_for(sale_price: Numeric, transaction: TransactionCosts) -> Decimal:
    return money(
        D(sale_price) * transaction.total_sale_percent + transaction.sale_closing_flat
    )


def compute_project_costs(
    *,
    purchase_price: Numeric,
    rehab_base: Numeric,
    rehab_contingency: Numeric,
    holding_months: int,
    transaction: TransactionCosts,
    holding: HoldingCosts,
    financing: FinancingTerms,
    sale_price: Optional[Numeric] = None,
    include_selling_costs: bool = True,
) -> ProjectCosts:
    """Price out one project.

    ``sale_price`` drives selling costs; pass ``include_selling_costs=False``
    for strategies that refinance instead of selling (BRRRR).
    """
    price = D(purchase_price)
    rehab = D(rehab_base)
    contingency_amount = rehab * D(rehab_contingency)
    rehab_total = rehab + contingency_amount

    acq_closing = price * transaction.purchase_closing_percent + transaction.purchase_closing_flat

    monthly_hold = holding.monthly_total
    hold_total = monthly_hold * D(holding_months)

    purchase_loan = price * financing.loan_to_purchase
    rehab_loan = rehab_total * financing.loan_to_rehab
    loan_total = purchase_loan + rehab_loan

    ifactor = interest_factor(
        financing.annual_interest_rate,
        financing.amortization_years,
        holding_months,
        financing.interest_only,
    )
    # Rehab funds draw down progressively, so only a fraction of the rehab loan
    # is outstanding on average across the hold.
    interest_cost = (
        purchase_loan * ifactor
        + rehab_loan * ifactor * financing.average_rehab_draw_factor
    )
    points_cost = loan_total * financing.points
    lender_fees = financing.lender_fees_flat if loan_total > 0 else ZERO
    financing_total = points_cost + interest_cost + lender_fees

    selling = ZERO
    if include_selling_costs and sale_price is not None:
        selling = D(sale_price) * transaction.total_sale_percent + transaction.sale_closing_flat

    misc = transaction.miscellaneous_costs

    total_project_cost = (
        price + rehab_total + acq_closing + hold_total + financing_total + selling + misc
    )
    total_basis = price + rehab_total + acq_closing + hold_total + financing_total + misc

    cash_required = (
        (price - purchase_loan)
        + (rehab_total - rehab_loan)
        + acq_closing
        + hold_total
        + financing_total
        + misc
    )

    return ProjectCosts(
        purchase_price=money(price),
        rehab_base=money(rehab),
        rehab_contingency_amount=money(contingency_amount),
        rehab_total=money(rehab_total),
        acquisition_closing_costs=money(acq_closing),
        monthly_holding_costs=money(monthly_hold),
        holding_months=int(holding_months),
        holding_costs=money(hold_total),
        financing=FinancingBreakdown(
            loan_amount=money(loan_total),
            purchase_loan=money(purchase_loan),
            rehab_loan=money(rehab_loan),
            points_cost=money(points_cost),
            interest_cost=money(interest_cost),
            lender_fees=money(lender_fees),
            total=money(financing_total),
        ),
        selling_costs=money(selling),
        miscellaneous_costs=money(misc),
        total_project_cost=money(total_project_cost),
        total_basis=money(total_basis),
        cash_required=money(cash_required),
    )


@dataclass(frozen=True)
class LinearModel:
    """``value = slope * purchase_price + intercept``."""

    slope: Decimal
    intercept: Decimal

    def at(self, purchase_price: Numeric) -> Decimal:
        return self.slope * D(purchase_price) + self.intercept

    def solve_for(self, target: Numeric) -> Optional[Decimal]:
        """Purchase price at which this model equals ``target``."""
        if self.slope == 0:
            return None
        return (D(target) - self.intercept) / self.slope


@dataclass(frozen=True)
class CostModel:
    """The cost stack expressed as linear functions of purchase price."""

    total_cost: LinearModel  # everything, including the purchase itself
    cash_required: LinearModel
    profit: LinearModel  # sale_price - total_cost


def build_cost_model(
    *,
    sale_price: Numeric,
    rehab_base: Numeric,
    rehab_contingency: Numeric,
    holding_months: int,
    transaction: TransactionCosts,
    holding: HoldingCosts,
    financing: FinancingTerms,
    include_selling_costs: bool = True,
) -> CostModel:
    """Express project economics as linear functions of the purchase price."""
    rehab = D(rehab_base)
    rehab_total = rehab * (D(1) + D(rehab_contingency))

    ifactor = interest_factor(
        financing.annual_interest_rate,
        financing.amortization_years,
        holding_months,
        financing.interest_only,
    )
    ltp = financing.loan_to_purchase
    ltr = financing.loan_to_rehab

    # Per-dollar-of-price cost of borrowing against the purchase.
    price_finance_slope = ltp * (financing.points + ifactor)
    rehab_finance_cost = rehab_total * ltr * (
        financing.points + ifactor * financing.average_rehab_draw_factor
    )
    lender_fees = financing.lender_fees_flat if (ltp > 0 or ltr > 0) else ZERO

    hold_total = holding.monthly_total * D(holding_months)
    selling = (
        D(sale_price) * transaction.total_sale_percent + transaction.sale_closing_flat
        if include_selling_costs
        else ZERO
    )
    misc = transaction.miscellaneous_costs

    fixed = (
        rehab_total
        + transaction.purchase_closing_flat
        + hold_total
        + rehab_finance_cost
        + lender_fees
        + selling
        + misc
    )

    total_cost = LinearModel(
        slope=D(1) + transaction.purchase_closing_percent + price_finance_slope,
        intercept=fixed,
    )
    cash_required = LinearModel(
        slope=(D(1) - ltp) + transaction.purchase_closing_percent + price_finance_slope,
        intercept=(
            rehab_total * (D(1) - ltr)
            + transaction.purchase_closing_flat
            + hold_total
            + rehab_finance_cost
            + lender_fees
            + misc
        ),
    )
    profit = LinearModel(slope=-total_cost.slope, intercept=D(sale_price) - fixed)
    return CostModel(total_cost=total_cost, cash_required=cash_required, profit=profit)


def max_price_for_profit(model: CostModel, target_profit: Numeric) -> Decimal:
    """Highest purchase price that still yields ``target_profit``."""
    solved = model.profit.solve_for(target_profit)
    return money(solved) if solved is not None else ZERO


def max_price_for_roi(model: CostModel, target_roi: Numeric) -> Optional[Decimal]:
    """Highest purchase price that still yields ``target_roi`` on cash invested.

    ``profit(P) = roi * cash(P)`` — both sides linear, so solve directly.
    """
    roi = D(target_roi)
    slope = model.profit.slope - roi * model.cash_required.slope
    intercept = roi * model.cash_required.intercept - model.profit.intercept
    if slope == 0:
        return None
    solved = intercept / slope
    # With no cash invested at the solution, a return "on cash" is undefined
    # and the constraint does not bind. Reporting a price here would present a
    # break-even purchase as if it satisfied a 20% return target.
    if model.cash_required.at(solved) <= 0:
        return None
    return money(solved)
