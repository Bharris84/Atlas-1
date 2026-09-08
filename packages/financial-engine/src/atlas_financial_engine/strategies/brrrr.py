"""BRRRR model — Buy, Rehab, Rent, Refinance, Repeat.

    purchase + rehab + closing + holding + financing = total project cost
    post-rehab value x refinance LTV                 = new loan
    new loan - refinance costs - acquisition payoff  = cash returned
    cash invested - cash returned                    = cash left in deal

The number that decides whether BRRRR is the right strategy is CASH LEFT IN
DEAL, not profit. A BRRRR that leaves $60k trapped in the property is a worse
outcome for an early-stage operator than a flip that returns everything, even
if the BRRRR creates more paper equity.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from ..confidence import assess_arv, assess_rehab, assess_rent
from ..costs import build_cost_model, compute_project_costs
from ..enums import Confidence, Strategy
from ..inputs import DealInputs
from ..loans import dscr as compute_dscr, monthly_payment
from ..money import D, MONTHS_PER_YEAR, ZERO, money, ratio, safe_div
from ..results import StrategyResult, criterion, not_viable
from .buy_hold import build_operating_statement


def analyze_brrrr(inputs: DealInputs) -> StrategyResult:
    a = inputs.assumptions
    b = a.brrrr

    price = inputs.purchase_price
    arv = inputs.effective_arv
    rehab = inputs.effective_rehab

    missing: List[str] = []
    if price is None:
        missing.append("purchase_price")
    if arv is None:
        missing.append("arv")
    if rehab is None:
        missing.append("rehab")
    if missing:
        return not_viable(
            Strategy.BRRRR,
            "BRRRR requires a purchase price, a post-rehab value and a rehab "
            "estimate.",
            missing,
        )

    costs = compute_project_costs(
        purchase_price=price,
        rehab_base=rehab,
        rehab_contingency=b.rehab_contingency,
        holding_months=b.seasoning_months,
        transaction=a.transaction,
        holding=a.holding,
        financing=b.acquisition_financing,
        include_selling_costs=False,
    )

    refinance_loan = money(D(arv) * b.refinance_ltv)
    refinance_costs = money(
        refinance_loan * b.refinance_closing_percent + b.refinance_closing_flat
    )
    acquisition_payoff = costs.financing.loan_amount
    cash_returned = money(refinance_loan - refinance_costs - acquisition_payoff)
    cash_invested = costs.cash_required
    cash_left_in_deal = money(cash_invested - cash_returned)

    equity_after_refinance = money(D(arv) - refinance_loan)
    equity_percent = safe_div(equity_after_refinance, arv)
    equity_percent = ratio(equity_percent) if equity_percent is not None else None
    equity_created = money(D(arv) - costs.total_basis)

    new_payment = monthly_payment(
        refinance_loan, b.refinance_rate, b.refinance_amortization_years
    )
    annual_debt_service = money(new_payment * MONTHS_PER_YEAR)

    rent = inputs.monthly_rent
    monthly_cash_flow: Optional[Decimal] = None
    annual_cash_flow: Optional[Decimal] = None
    ratio_dscr: Optional[Decimal] = None
    ops_dict: Optional[Dict[str, Any]] = None
    noi: Optional[Decimal] = None
    warnings: List[str] = []

    if rent is not None:
        ops = build_operating_statement(rent, a.rental)
        ops_dict = ops.to_dict()
        noi = ops.net_operating_income
        annual_cash_flow = money(noi - annual_debt_service)
        monthly_cash_flow = money(annual_cash_flow / MONTHS_PER_YEAR)
        ratio_dscr = compute_dscr(noi, annual_debt_service)
    else:
        warnings.append(
            "No rent estimate: the refinance and equity figures are computed, but "
            "cash flow and DSCR cannot be."
        )

    # Cash-on-cash on money actually left in the deal. When nothing is left,
    # the return is undefined rather than infinite, and is reported as such.
    coc: Optional[Decimal] = None
    if annual_cash_flow is not None and cash_left_in_deal > 0:
        coc = safe_div(annual_cash_flow, cash_left_in_deal)
        coc = ratio(coc) if coc is not None else None
    elif annual_cash_flow is not None and cash_left_in_deal <= 0:
        warnings.append(
            "The refinance returns all invested capital, so cash-on-cash return is "
            "undefined (no cash remains in the deal)."
        )

    # Highest purchase price that still meets the cash-left ceiling.
    model = build_cost_model(
        sale_price=arv,
        rehab_base=rehab,
        rehab_contingency=b.rehab_contingency,
        holding_months=b.seasoning_months,
        transaction=a.transaction,
        holding=a.holding,
        financing=b.acquisition_financing,
        include_selling_costs=False,
    )
    fin = b.acquisition_financing
    rehab_total = D(rehab) * (D(1) + b.rehab_contingency)
    refi_net = refinance_loan - refinance_costs
    slope = model.cash_required.slope + fin.loan_to_purchase
    max_purchase_price: Optional[Decimal] = None
    if slope > 0:
        max_purchase_price = money(
            (
                b.max_cash_left_in_deal
                + refi_net
                - rehab_total * fin.loan_to_rehab
                - model.cash_required.intercept
            )
            / slope
        )

    arv_conf = assess_arv(inputs.evidence, inputs.arv_low, inputs.arv_high)
    rehab_conf = assess_rehab(inputs.evidence, inputs.rehab_low, inputs.rehab_high)
    rent_conf = assess_rent(inputs.evidence)
    confidence = Confidence.weakest(arv_conf.level, rehab_conf.level, rent_conf.level)

    if cash_left_in_deal > b.max_cash_left_in_deal:
        warnings.append(
            f"${cash_left_in_deal:,.0f} stays trapped in this property, above the "
            f"${b.max_cash_left_in_deal:,.0f} ceiling. That is capital unavailable "
            "for the next deal."
        )
    if arv_conf.level != Confidence.HIGH:
        warnings.append(
            "The refinance depends on an appraiser agreeing with this ARV. "
            "Confidence in the value is not high, so the cash-out is uncertain."
        )

    criteria = [
        criterion(
            "max_cash_left_in_deal",
            "Maximum cash left in deal",
            b.max_cash_left_in_deal,
            cash_left_in_deal,
            higher_is_better=False,
        ),
        criterion(
            "minimum_equity_percent",
            "Minimum equity after refinance",
            b.minimum_equity_percent,
            equity_percent,
            unit="percent",
        ),
        criterion(
            "minimum_monthly_cash_flow",
            "Minimum monthly cash flow",
            a.rental.minimum_monthly_cash_flow,
            monthly_cash_flow,
        ),
        criterion(
            "target_dscr", "Target DSCR", a.rental.target_dscr, ratio_dscr, unit="ratio"
        ),
    ]
    meets = all(c.met for c in criteria)

    return StrategyResult(
        strategy=Strategy.BRRRR,
        viable=True,
        # Profit means REALISED profit. Equity created by a rehab is real but
        # unrealised — it is reported in ``equity_created`` and scored there.
        # Counting it as profit as well would double-count it against a flip,
        # where the same equity is actually converted to cash.
        profit=annual_cash_flow,
        cash_required=cash_left_in_deal if cash_left_in_deal > 0 else ZERO,
        roi=coc,
        annualized_roi=coc,
        monthly_cash_flow=monthly_cash_flow,
        annual_cash_flow=annual_cash_flow,
        equity_created=equity_created,
        dscr=ratio_dscr,
        cap_rate=(ratio(safe_div(noi, price)) if noi is not None else None),
        cash_on_cash=coc,
        max_purchase_price=max_purchase_price,
        time_to_liquidity_months=b.seasoning_months,
        meets_criteria=meets,
        criteria=criteria,
        confidence=confidence,
        confidence_reasons=arv_conf.reasons + rehab_conf.reasons + rent_conf.reasons,
        warnings=warnings,
        detail={
            "arv": str(arv),
            "costs": costs.to_dict(),
            "total_project_cost": str(costs.total_project_cost),
            "cash_invested": str(cash_invested),
            "refinance_ltv": str(b.refinance_ltv),
            "refinance_loan": str(refinance_loan),
            "refinance_costs": str(refinance_costs),
            "acquisition_loan_payoff": str(acquisition_payoff),
            "cash_returned": str(cash_returned),
            "cash_left_in_deal": str(cash_left_in_deal),
            "equity_created": str(equity_created),
            "equity_after_refinance": str(equity_after_refinance),
            "equity_percent": str(equity_percent) if equity_percent is not None else None,
            "new_monthly_payment": str(new_payment),
            "annual_debt_service": str(annual_debt_service),
            "operating_statement": ops_dict,
            "seasoning_months": b.seasoning_months,
            "arv_confidence": arv_conf.to_dict(),
            "rehab_confidence": rehab_conf.to_dict(),
        },
    )
