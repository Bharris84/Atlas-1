"""Buy & hold rental model.

    Gross scheduled rent
      - vacancy
    = effective gross income
      - management, maintenance, CapEx, taxes, insurance, HOA, other
    = NOI
      - debt service
    = cash flow

Two conventions worth stating explicitly, because different investors use
different ones and the difference is material:

* Management is charged on COLLECTED rent (effective gross income), which is
  how management agreements are actually written.
* Maintenance and CapEx reserves are charged on GROSS SCHEDULED rent, because
  a vacant unit still ages.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional

from ..assumptions import Assumptions, RentalAssumptions, known
from ..confidence import assess_arv, assess_rent
from ..enums import Confidence, Strategy
from ..inputs import DealInputs
from ..loans import dscr as compute_dscr, monthly_payment, payment_factor
from ..money import D, MONTHS_PER_YEAR, Numeric, ZERO, money, ratio, safe_div
from ..results import StrategyResult, criterion, not_viable


@dataclass(frozen=True)
class OperatingStatement:
    gross_scheduled_rent: Decimal
    vacancy_loss: Decimal
    effective_gross_income: Decimal
    management: Decimal
    maintenance: Decimal
    capex: Decimal
    taxes: Decimal
    insurance: Decimal
    hoa: Decimal
    other: Decimal
    total_operating_expenses: Decimal
    net_operating_income: Decimal

    def to_dict(self) -> Dict[str, Any]:
        return {k: str(v) for k, v in self.__dict__.items()}


def build_operating_statement(
    monthly_rent: Numeric, rental: RentalAssumptions
) -> OperatingStatement:
    """Annual operating statement from a monthly rent figure."""
    gsr = D(monthly_rent) * MONTHS_PER_YEAR
    vacancy = gsr * rental.vacancy_percent
    egi = gsr - vacancy
    management = egi * rental.management_percent
    maintenance = gsr * rental.maintenance_percent
    capex = gsr * rental.capex_percent
    # Unknown expenses are omitted, not guessed. That overstates NOI, which is
    # why analyze_buy_hold reports them and the risk engine blocks on them.
    taxes = known(rental.annual_taxes)
    insurance = known(rental.annual_insurance)
    hoa = known(rental.monthly_hoa) * MONTHS_PER_YEAR
    other = rental.annual_other_expenses
    opex = management + maintenance + capex + taxes + insurance + hoa + other
    noi = egi - opex
    return OperatingStatement(
        gross_scheduled_rent=money(gsr),
        vacancy_loss=money(vacancy),
        effective_gross_income=money(egi),
        management=money(management),
        maintenance=money(maintenance),
        capex=money(capex),
        taxes=money(taxes),
        insurance=money(insurance),
        hoa=money(hoa),
        other=money(other),
        total_operating_expenses=money(opex),
        net_operating_income=money(noi),
    )


def _max_price(
    noi: Decimal,
    rental: RentalAssumptions,
    assumptions: Assumptions,
    rehab: Decimal,
) -> Dict[str, Optional[Decimal]]:
    """Highest purchase price satisfying each rental constraint."""
    fin = rental.financing
    ltp = fin.loan_to_purchase
    factor = (
        payment_factor(fin.annual_interest_rate, fin.amortization_years)
        if not fin.interest_only
        else fin.annual_interest_rate / MONTHS_PER_YEAR
    )
    annual_debt_per_dollar = ltp * factor * MONTHS_PER_YEAR

    tx = assumptions.transaction
    cash_slope = (D(1) - ltp) + tx.purchase_closing_percent + fin.points * ltp
    cash_intercept = (
        tx.purchase_closing_flat
        + rehab
        + (fin.lender_fees_flat if ltp > 0 else ZERO)
        + tx.miscellaneous_costs
    )

    results: Dict[str, Optional[Decimal]] = {
        "cash_flow": None,
        "dscr": None,
        "cash_on_cash": None,
    }

    if annual_debt_per_dollar > 0:
        target_cf = rental.minimum_monthly_cash_flow * MONTHS_PER_YEAR
        results["cash_flow"] = money((noi - target_cf) / annual_debt_per_dollar)
        if rental.target_dscr > 0:
            results["dscr"] = money(noi / (rental.target_dscr * annual_debt_per_dollar))

    coc_denominator = annual_debt_per_dollar + rental.minimum_cash_on_cash * cash_slope
    if coc_denominator > 0:
        results["cash_on_cash"] = money(
            (noi - rental.minimum_cash_on_cash * cash_intercept) / coc_denominator
        )
    return results


def analyze_buy_hold(inputs: DealInputs) -> StrategyResult:
    a = inputs.assumptions
    rental = a.rental
    fin = rental.financing

    price = inputs.purchase_price
    rent = inputs.monthly_rent

    missing: List[str] = []
    if price is None:
        missing.append("purchase_price")
    if rent is None:
        missing.append("monthly_rent")
    if missing:
        return not_viable(
            Strategy.BUY_HOLD,
            "A rental cannot be underwritten without a purchase price and a rent "
            "estimate.",
            missing,
        )

    rehab = inputs.effective_rehab or ZERO
    ops = build_operating_statement(rent, rental)
    noi = ops.net_operating_income

    loan = D(price) * fin.loan_to_purchase
    payment = monthly_payment(
        loan, fin.annual_interest_rate, fin.amortization_years, fin.interest_only
    )
    annual_debt_service = money(payment * MONTHS_PER_YEAR)
    annual_cash_flow = money(noi - annual_debt_service)
    monthly_cash_flow = money(annual_cash_flow / MONTHS_PER_YEAR)

    acquisition_closing = money(
        D(price) * a.transaction.purchase_closing_percent
        + a.transaction.purchase_closing_flat
    )
    points_cost = money(loan * fin.points)
    lender_fees = fin.lender_fees_flat if loan > 0 else ZERO
    down_payment = money(D(price) - loan)
    cash_required = money(
        down_payment
        + acquisition_closing
        + rehab
        + points_cost
        + lender_fees
        + a.transaction.miscellaneous_costs
    )

    value = inputs.effective_arv or D(price)
    cap_rate = safe_div(noi, price)
    cap_rate = ratio(cap_rate) if cap_rate is not None else None
    cap_rate_on_value = safe_div(noi, value)
    coc = safe_div(annual_cash_flow, cash_required)
    coc = ratio(coc) if coc is not None else None
    ratio_dscr = compute_dscr(noi, annual_debt_service)
    equity = money(D(value) - loan)

    max_prices = _max_price(noi, rental, a, rehab)
    candidates = [p for p in max_prices.values() if p is not None]
    max_purchase_price = min(candidates) if candidates else None

    arv_conf = assess_arv(inputs.evidence, inputs.arv_low, inputs.arv_high)
    rent_conf = assess_rent(inputs.evidence)
    confidence = Confidence.weakest(rent_conf.level, arv_conf.level)

    warnings: List[str] = []
    if annual_cash_flow < 0:
        warnings.append(
            "Negative cash flow: this rental requires ongoing capital to hold."
        )
    unknown_expenses = rental.unknown_fields()
    if "annual_taxes" in unknown_expenses:
        warnings.append(
            "Property taxes are not known and have been left out of this NOI. "
            "Every US property is taxed, so the cash flow above is overstated "
            "until a real figure is entered."
        )
    if "annual_insurance" in unknown_expenses:
        warnings.append(
            "Insurance is not known and has been left out of this NOI. Coastal "
            "and older-home premiums can change this analysis materially."
        )
    if "monthly_hoa" in unknown_expenses:
        warnings.append(
            "HOA dues are not known. Enter 0 if the property has no association, "
            "so this stops being reported as an open question."
        )
    if ratio_dscr is not None and ratio_dscr < D("1.0"):
        warnings.append(
            "DSCR is below 1.0 — the property does not cover its own debt service."
        )

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
        strategy=Strategy.BUY_HOLD,
        viable=True,
        profit=annual_cash_flow,
        cash_required=cash_required,
        roi=coc,
        annualized_roi=coc,
        monthly_cash_flow=monthly_cash_flow,
        annual_cash_flow=annual_cash_flow,
        equity_created=money(D(value) - D(price) - rehab),
        dscr=ratio_dscr,
        cap_rate=cap_rate,
        cash_on_cash=coc,
        max_purchase_price=max_purchase_price,
        # A rental is the least liquid exit modelled here; a sale takes months.
        time_to_liquidity_months=None,
        meets_criteria=meets,
        criteria=criteria,
        confidence=confidence,
        confidence_reasons=rent_conf.reasons + arv_conf.reasons,
        warnings=warnings,
        detail={
            "operating_statement": ops.to_dict(),
            "monthly_payment": str(payment),
            "annual_debt_service": str(annual_debt_service),
            "loan_amount": str(money(loan)),
            "down_payment": str(down_payment),
            "acquisition_closing_costs": str(acquisition_closing),
            "points_cost": str(points_cost),
            "lender_fees": str(money(lender_fees)),
            "rehab": str(money(rehab)),
            "cash_required": str(cash_required),
            "cap_rate": str(cap_rate) if cap_rate is not None else None,
            "cap_rate_on_value": (
                str(ratio(cap_rate_on_value)) if cap_rate_on_value is not None else None
            ),
            "value_used": str(money(value)),
            "equity": str(equity),
            "max_price_for_cash_flow": (
                str(max_prices["cash_flow"]) if max_prices["cash_flow"] else None
            ),
            "max_price_for_dscr": (
                str(max_prices["dscr"]) if max_prices["dscr"] else None
            ),
            "max_price_for_cash_on_cash": (
                str(max_prices["cash_on_cash"]) if max_prices["cash_on_cash"] else None
            ),
            "rent_confidence": rent_conf.to_dict(),
        },
    )
