"""Wholesale model — underwritten from the END BUYER's deal.

Atlas deliberately does not use the "70% rule". That rule is a compressed
approximation of a real calculation, and the approximation breaks in exactly
the markets Atlas targets: low price points where fixed costs dominate, and
heavy rehabs where the rehab-to-ARV ratio is far from typical.

Instead:

    1. Model the flip the end buyer would actually be doing.
    2. Solve for the highest price at which that buyer still earns their
       required profit.  -> maximum end-buyer purchase price
    3. Subtract our assignment fee and a risk buffer.
       -> maximum allowable contract price

The buffer exists because the buyer's own inspection will find things ours
did not, and because a contract we cannot assign is worth less than nothing.
"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from ..confidence import assess_arv, assess_rehab
from ..costs import build_cost_model, max_price_for_profit
from ..enums import Confidence, Strategy
from ..inputs import DealInputs
from ..money import D, ZERO, money, ratio, safe_div
from ..results import StrategyResult, criterion, not_viable


def analyze_wholesale(inputs: DealInputs) -> StrategyResult:
    a = inputs.assumptions
    w = a.wholesale

    arv = inputs.effective_arv
    rehab = inputs.effective_rehab
    price = inputs.purchase_price

    missing: List[str] = []
    if arv is None:
        missing.append("arv")
    if rehab is None:
        missing.append("rehab")
    if missing:
        return not_viable(
            Strategy.WHOLESALE,
            "Wholesale economics are derived from the end buyer's flip, which "
            "requires an ARV and a rehab estimate.",
            missing,
        )

    # Step 1 & 2: the end buyer's deal.
    buyer_profit_target = max(
        D(arv) * w.buyer_profit_percent_of_arv, w.buyer_profit_floor
    )
    buyer_model = build_cost_model(
        sale_price=arv,
        rehab_base=rehab,
        rehab_contingency=w.buyer_rehab_contingency,
        holding_months=w.buyer_holding_months,
        transaction=a.transaction,
        holding=a.holding,
        financing=w.buyer_financing,
    )
    max_buyer_price = max_price_for_profit(buyer_model, buyer_profit_target)
    buyer_costs_at_max = money(
        buyer_model.total_cost.at(max_buyer_price) - max_buyer_price
    )

    # Step 3: our contract price.
    risk_buffer = money(D(arv) * w.risk_buffer_percent_of_arv + w.risk_buffer_flat)
    max_contract_price = money(
        max_buyer_price - w.target_assignment_fee - risk_buffer
    )

    warnings: List[str] = []
    achievable_fee: Optional[Decimal] = None
    profit: Optional[Decimal] = None
    spread: Optional[Decimal] = None

    if price is not None:
        spread = money(max_buyer_price - D(price))
        achievable_fee = money(max(spread - risk_buffer, ZERO))
        profit = money(achievable_fee - w.wholesale_transaction_costs)
        if spread <= 0:
            warnings.append(
                "There is no spread: the contract price is at or above what an "
                "investor buyer could pay and still hit their return."
            )
        elif achievable_fee < w.target_assignment_fee:
            warnings.append(
                "Spread is thinner than the target assignment fee once the risk "
                "buffer is held back."
            )
    else:
        warnings.append(
            "No contract price entered — showing the maximum allowable offer only."
        )

    if max_buyer_price <= 0:
        warnings.append(
            "The end buyer's own numbers do not work at any purchase price above "
            "zero; this property does not support a resale to an investor."
        )

    arv_conf = assess_arv(inputs.evidence, inputs.arv_low, inputs.arv_high)
    rehab_conf = assess_rehab(inputs.evidence, inputs.rehab_low, inputs.rehab_high)
    confidence = Confidence.weakest(arv_conf.level, rehab_conf.level)
    if confidence == Confidence.LOW:
        warnings.append(
            "Low confidence in ARV or rehab means the buyer's maximum price is "
            "itself uncertain; verify before contracting."
        )

    criteria = [
        criterion(
            "target_assignment_fee",
            "Target assignment fee",
            w.target_assignment_fee,
            achievable_fee,
        )
    ]
    meets = all(c.met for c in criteria)

    roi = None
    if profit is not None and w.wholesale_transaction_costs > 0:
        roi = safe_div(profit, w.wholesale_transaction_costs)
        roi = ratio(roi) if roi is not None else None

    return StrategyResult(
        strategy=Strategy.WHOLESALE,
        viable=True,
        profit=profit,
        # Wholesaling is the capital-light strategy: the only money at risk is
        # earnest money plus marketing, not a down payment.
        cash_required=money(w.wholesale_transaction_costs),
        roi=roi,
        equity_created=ZERO,
        max_purchase_price=max_contract_price,
        time_to_liquidity_months=1,
        meets_criteria=meets,
        criteria=criteria,
        confidence=confidence,
        confidence_reasons=arv_conf.reasons + rehab_conf.reasons,
        warnings=warnings,
        detail={
            "arv": str(arv),
            "rehab": str(rehab),
            "buyer_rehab_total": str(
                money(D(rehab) * (D(1) + w.buyer_rehab_contingency))
            ),
            "buyer_profit_target": str(money(buyer_profit_target)),
            "buyer_profit_percent_of_arv": str(w.buyer_profit_percent_of_arv),
            "buyer_costs": str(buyer_costs_at_max),
            "max_buyer_purchase_price": str(max_buyer_price),
            "target_assignment_fee": str(money(w.target_assignment_fee)),
            "risk_buffer": str(risk_buffer),
            "max_allowable_contract_price": str(max_contract_price),
            "contract_price": str(money(price)) if price is not None else None,
            "spread_to_buyer_max": str(spread) if spread is not None else None,
            "estimated_assignment_fee": (
                str(achievable_fee) if achievable_fee is not None else None
            ),
            "estimated_wholesale_profit": str(profit) if profit is not None else None,
            "buyer_holding_months": w.buyer_holding_months,
            "arv_confidence": arv_conf.to_dict(),
            "rehab_confidence": rehab_conf.to_dict(),
        },
    )
