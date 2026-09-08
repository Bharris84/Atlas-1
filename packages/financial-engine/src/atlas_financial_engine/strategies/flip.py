"""Fix & flip model.

    ARV
      - purchase price
      - rehab (incl. contingency)
      - acquisition closing costs
      - financing costs
      - holding costs
      - selling costs
      - miscellaneous
    = net profit

ROI is measured against CASH INVESTED, not total project cost. With leverage
those are very different numbers, and cash invested is the one that constrains
how many deals can run at once.
"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from ..confidence import assess_arv, assess_rehab
from ..costs import build_cost_model, compute_project_costs, max_price_for_profit, max_price_for_roi
from ..enums import Confidence, Strategy
from ..inputs import DealInputs
from ..money import D, ZERO, money, ratio, safe_div
from ..results import StrategyResult, criterion, not_viable


def analyze_flip(inputs: DealInputs) -> StrategyResult:
    a = inputs.assumptions
    flip = a.flip

    arv = inputs.effective_arv
    rehab = inputs.effective_rehab
    price = inputs.purchase_price

    missing: List[str] = []
    if price is None:
        missing.append("purchase_price")
    if arv is None:
        missing.append("arv")
    if rehab is None:
        missing.append("rehab")
    if missing:
        return not_viable(
            Strategy.FLIP,
            "A flip cannot be underwritten without a purchase price, an ARV and a "
            "rehab estimate.",
            missing,
        )

    costs = compute_project_costs(
        purchase_price=price,
        rehab_base=rehab,
        rehab_contingency=flip.rehab_contingency,
        holding_months=flip.holding_months,
        transaction=a.transaction,
        holding=a.holding,
        financing=flip.financing,
        sale_price=arv,
    )

    net_profit = money(D(arv) - costs.total_project_cost)
    cash_required = costs.cash_required
    roi = safe_div(net_profit, cash_required)
    roi = ratio(roi) if roi is not None else None
    profit_margin = safe_div(net_profit, arv)
    profit_margin = ratio(profit_margin) if profit_margin is not None else None

    months = flip.holding_months
    annualized_roi: Optional[Decimal] = None
    if roi is not None and months > 0:
        annualized_roi = ratio(roi * D(12) / D(months))

    model = build_cost_model(
        sale_price=arv,
        rehab_base=rehab,
        rehab_contingency=flip.rehab_contingency,
        holding_months=months,
        transaction=a.transaction,
        holding=a.holding,
        financing=flip.financing,
    )
    price_for_profit = max_price_for_profit(model, flip.minimum_net_profit)
    price_for_roi = max_price_for_roi(model, flip.minimum_roi)
    candidates = [p for p in (price_for_profit, price_for_roi) if p is not None]
    max_purchase_price = min(candidates) if candidates else None
    if max_purchase_price is not None and max_purchase_price < 0:
        max_purchase_price = ZERO

    arv_conf = assess_arv(inputs.evidence, inputs.arv_low, inputs.arv_high)
    rehab_conf = assess_rehab(inputs.evidence, inputs.rehab_low, inputs.rehab_high)
    confidence = Confidence.weakest(arv_conf.level, rehab_conf.level)

    warnings: List[str] = []
    if net_profit < 0:
        warnings.append(
            "This flip loses money at the entered purchase price before any "
            "surprises are accounted for."
        )
    if rehab > 0 and arv > 0 and (D(rehab) / D(arv)) > D("0.35"):
        warnings.append(
            "Rehab exceeds 35% of ARV — a heavy rehab where estimate error is "
            "usually the dominant risk."
        )
    if profit_margin is not None and profit_margin < D("0.10"):
        warnings.append(
            "Profit margin is under 10% of ARV; a small ARV miss wipes out the deal."
        )
    if max_purchase_price is not None and price > max_purchase_price:
        warnings.append(
            f"Purchase price exceeds the maximum that meets the flip buy box "
            f"(${max_purchase_price:,.0f})."
        )

    criteria = [
        criterion(
            "minimum_net_profit",
            "Minimum net profit",
            flip.minimum_net_profit,
            net_profit,
        ),
        criterion("minimum_roi", "Minimum ROI", flip.minimum_roi, roi, unit="percent"),
    ]
    meets = all(c.met for c in criteria)

    return StrategyResult(
        strategy=Strategy.FLIP,
        viable=True,
        profit=net_profit,
        cash_required=cash_required,
        roi=roi,
        annualized_roi=annualized_roi,
        equity_created=money(D(arv) - costs.total_basis),
        max_purchase_price=max_purchase_price,
        time_to_liquidity_months=months,
        meets_criteria=meets,
        criteria=criteria,
        confidence=confidence,
        confidence_reasons=arv_conf.reasons + rehab_conf.reasons,
        warnings=warnings,
        detail={
            "arv": str(arv),
            "costs": costs.to_dict(),
            "net_profit": str(net_profit),
            "profit_margin": str(profit_margin) if profit_margin is not None else None,
            "total_project_cost": str(costs.total_project_cost),
            "max_price_for_minimum_profit": str(price_for_profit),
            "max_price_for_minimum_roi": (
                str(price_for_roi) if price_for_roi is not None else None
            ),
            "arv_confidence": arv_conf.to_dict(),
            "rehab_confidence": rehab_conf.to_dict(),
            "holding_months": months,
        },
    )
