"""Seller-financing model (buy-side).

Models acquiring a property on terms from the seller and holding it as a
rental. This is the capital-light path to ownership: the down payment and
closing costs are the whole cash outlay, and there is no lender underwriting
the borrower.

The balloon is modelled explicitly. A seller-financed deal with a five-year
balloon is a five-year commitment to either refinance or sell, and the balance
due on that date is a number the operator must see up front, not discover.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from ..confidence import assess_arv, assess_rent
from ..enums import Confidence, Strategy
from ..inputs import DealInputs
from ..loans import (
    dscr as compute_dscr,
    monthly_payment,
    remaining_balance,
    total_interest_paid,
)
from ..money import D, MONTHS_PER_YEAR, ZERO, money, ratio, safe_div
from ..results import StrategyResult, criterion, not_viable
from .buy_hold import build_operating_statement


def analyze_seller_finance(inputs: DealInputs) -> StrategyResult:
    a = inputs.assumptions
    sf = a.seller_finance
    rental = a.rental

    price = inputs.purchase_price
    if price is None:
        return not_viable(
            Strategy.SELLER_FINANCE,
            "Seller financing requires a purchase price.",
            ["purchase_price"],
        )

    down_payment = money(D(price) * sf.down_payment_percent)
    financed_amount = money(D(price) - down_payment)
    payment = monthly_payment(
        financed_amount, sf.annual_interest_rate, sf.amortization_years
    )
    annual_debt_service = money(payment * MONTHS_PER_YEAR)

    closing_costs = money(
        D(price) * sf.closing_costs_percent + a.transaction.purchase_closing_flat
    )
    rehab = inputs.effective_rehab or ZERO
    cash_required = money(down_payment + closing_costs + rehab)

    balloon_months = sf.balloon_years * 12 if sf.balloon_years else None
    balloon_balance: Optional[Decimal] = None
    interest_through_balloon: Optional[Decimal] = None
    if balloon_months:
        balloon_balance = remaining_balance(
            financed_amount,
            sf.annual_interest_rate,
            sf.amortization_years,
            balloon_months,
        )
        interest_through_balloon = total_interest_paid(
            financed_amount,
            sf.annual_interest_rate,
            sf.amortization_years,
            balloon_months,
        )

    warnings: List[str] = []
    rent = inputs.monthly_rent
    monthly_cash_flow: Optional[Decimal] = None
    annual_cash_flow: Optional[Decimal] = None
    ratio_dscr: Optional[Decimal] = None
    ops_dict: Optional[Dict[str, Any]] = None
    coc: Optional[Decimal] = None
    noi: Optional[Decimal] = None

    if rent is not None:
        ops = build_operating_statement(rent, rental)
        ops_dict = ops.to_dict()
        noi = ops.net_operating_income
        annual_cash_flow = money(noi - annual_debt_service)
        monthly_cash_flow = money(annual_cash_flow / MONTHS_PER_YEAR)
        ratio_dscr = compute_dscr(noi, annual_debt_service)
        coc = safe_div(annual_cash_flow, cash_required)
        coc = ratio(coc) if coc is not None else None
        if annual_cash_flow < 0:
            warnings.append(
                "Negative cash flow on these terms; the payment structure needs to "
                "change or the price does."
            )
    else:
        warnings.append(
            "No rent estimate: payment and balloon are computed, but cash flow "
            "cannot be."
        )

    value = inputs.effective_arv or D(price)
    equity_at_close = money(D(value) - financed_amount)

    if balloon_balance is not None and balloon_balance > 0:
        warnings.append(
            f"A balloon payment of ${balloon_balance:,.0f} comes due in "
            f"{sf.balloon_years} years. Plan the refinance or sale now, not then."
        )
    if sf.annual_interest_rate > D("0.10"):
        warnings.append(
            "Seller rate above 10% erodes most of the advantage of buying on terms."
        )
    if inputs.effective_arv is not None and D(price) > D(inputs.effective_arv):
        warnings.append(
            "Purchase price exceeds the estimated value. Paying above value can be "
            "rational on favourable terms, but it is a deliberate trade, not a win."
        )

    arv_conf = assess_arv(inputs.evidence, inputs.arv_low, inputs.arv_high)
    rent_conf = assess_rent(inputs.evidence)
    confidence = Confidence.weakest(rent_conf.level, arv_conf.level)

    criteria = [
        criterion(
            "minimum_monthly_cash_flow",
            "Minimum monthly cash flow",
            rental.minimum_monthly_cash_flow,
            monthly_cash_flow,
        ),
        criterion(
            "minimum_cash_on_cash",
            "Minimum cash-on-cash return",
            rental.minimum_cash_on_cash,
            coc,
            unit="percent",
        ),
        criterion(
            "target_dscr", "Target DSCR", rental.target_dscr, ratio_dscr, unit="ratio"
        ),
    ]
    meets = all(c.met for c in criteria)

    return StrategyResult(
        strategy=Strategy.SELLER_FINANCE,
        viable=True,
        profit=annual_cash_flow,
        cash_required=cash_required,
        roi=coc,
        annualized_roi=coc,
        monthly_cash_flow=monthly_cash_flow,
        annual_cash_flow=annual_cash_flow,
        equity_created=money(D(value) - D(price) - rehab),
        dscr=ratio_dscr,
        cap_rate=(ratio(safe_div(noi, price)) if noi is not None else None),
        cash_on_cash=coc,
        max_purchase_price=None,
        time_to_liquidity_months=balloon_months,
        meets_criteria=meets,
        criteria=criteria,
        confidence=confidence,
        confidence_reasons=rent_conf.reasons + arv_conf.reasons,
        warnings=warnings,
        detail={
            "purchase_price": str(money(price)),
            "down_payment": str(down_payment),
            "down_payment_percent": str(sf.down_payment_percent),
            "financed_amount": str(financed_amount),
            "annual_interest_rate": str(sf.annual_interest_rate),
            "amortization_years": sf.amortization_years,
            "balloon_years": sf.balloon_years,
            "monthly_principal_and_interest": str(payment),
            "annual_debt_service": str(annual_debt_service),
            "closing_costs": str(closing_costs),
            "cash_required": str(cash_required),
            "balloon_balance": str(balloon_balance) if balloon_balance is not None else None,
            "interest_paid_through_balloon": (
                str(interest_through_balloon)
                if interest_through_balloon is not None
                else None
            ),
            "equity_at_close": str(equity_at_close),
            "operating_statement": ops_dict,
        },
    )
