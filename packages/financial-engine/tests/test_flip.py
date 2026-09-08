"""Fix & flip model."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from atlas_financial_engine import (
    DealInputs,
    FlipAssumptions,
    Strategy,
    analyze_flip,
)
from atlas_financial_engine.assumptions import CASH_PURCHASE, DEFAULT_HARD_MONEY
from atlas_financial_engine.money import D


class TestProfitCalculation:
    def test_profit_is_arv_minus_every_cost(self, baseline: DealInputs):
        result = analyze_flip(baseline)
        costs = result.detail["costs"]
        assert result.profit == D("250000") - D(costs["total_project_cost"])

    def test_contingency_is_included_in_the_rehab_actually_spent(
        self, baseline: DealInputs
    ):
        costs = analyze_flip(baseline).detail["costs"]
        assert D(costs["rehab_total"]) == D("45000") * D("1.15")

    def test_removing_contingency_increases_profit_by_the_contingency(
        self, baseline: DealInputs
    ):
        no_contingency = replace(
            baseline,
            assumptions=replace(
                baseline.assumptions, flip=FlipAssumptions(rehab_contingency=D("0"))
            ),
        )
        delta = analyze_flip(no_contingency).profit - analyze_flip(baseline).profit
        # The contingency itself is $6,750, and the rehab loan funds it, so
        # dropping it also drops the points and interest charged on it.
        points_saved = D("6750") * D("0.02")
        interest_saved = D("6750") * D("0.11") / 12 * 6 * D("0.60")
        assert abs(delta - (D("6750") + points_saved + interest_saved)) < D("0.02")

    def test_roi_is_measured_against_cash_invested_not_project_cost(
        self, baseline: DealInputs
    ):
        result = analyze_flip(baseline)
        assert abs(result.roi - result.profit / result.cash_required) < D("0.0001")

    def test_annualized_roi_scales_a_six_month_hold(self, baseline: DealInputs):
        result = analyze_flip(baseline)
        assert abs(result.annualized_roi - result.roi * 2) < D("0.0002")

    def test_longer_hold_costs_money(self, baseline: DealInputs):
        slow = replace(
            baseline,
            assumptions=replace(
                baseline.assumptions, flip=FlipAssumptions(holding_months=12)
            ),
        )
        assert analyze_flip(slow).profit < analyze_flip(baseline).profit


class TestLeverage:
    def test_cash_purchase_needs_more_money_but_earns_more_profit(
        self, baseline: DealInputs
    ):
        all_cash = replace(
            baseline,
            assumptions=replace(
                baseline.assumptions, flip=FlipAssumptions(financing=CASH_PURCHASE)
            ),
        )
        cash_result = analyze_flip(all_cash)
        levered = analyze_flip(baseline)
        assert cash_result.cash_required > levered.cash_required
        assert cash_result.profit > levered.profit
        # ...but leverage is what produces the higher return on cash.
        assert levered.roi > cash_result.roi


class TestMaxPurchasePrice:
    def test_buying_at_max_price_meets_the_buy_box(self, baseline: DealInputs):
        max_price = analyze_flip(baseline).max_purchase_price
        at_max = analyze_flip(replace(baseline, purchase_price=max_price))
        assert at_max.meets_criteria is True

    def test_max_price_is_the_binding_constraint_of_profit_and_roi(
        self, baseline: DealInputs
    ):
        result = analyze_flip(baseline)
        d = result.detail
        candidates = [D(d["max_price_for_minimum_profit"])]
        if d["max_price_for_minimum_roi"] is not None:
            candidates.append(D(d["max_price_for_minimum_roi"]))
        assert result.max_purchase_price == min(candidates)

    def test_at_max_price_profit_or_roi_sits_exactly_on_target(self, baseline: DealInputs):
        at_max = analyze_flip(
            replace(baseline, purchase_price=analyze_flip(baseline).max_purchase_price)
        )
        flip = baseline.assumptions.flip
        on_profit = abs(at_max.profit - flip.minimum_net_profit) < D("1.00")
        on_roi = abs(at_max.roi - flip.minimum_roi) < D("0.001")
        assert on_profit or on_roi

    def test_paying_over_max_price_warns(self, baseline: DealInputs):
        over = replace(
            baseline, purchase_price=analyze_flip(baseline).max_purchase_price + D("20000")
        )
        assert any("exceeds the maximum" in w for w in analyze_flip(over).warnings)


class TestBuyBox:
    def test_meets_criteria_when_profit_and_roi_clear_targets(self, baseline: DealInputs):
        good = replace(baseline, purchase_price=D("110000"))
        result = analyze_flip(good)
        assert result.profit > D("30000")
        assert result.meets_criteria is True

    def test_criteria_are_reported_with_targets_and_actuals(self, baseline: DealInputs):
        criteria = {c.name: c for c in analyze_flip(baseline).criteria}
        assert criteria["minimum_net_profit"].target == D("30000")
        assert criteria["minimum_roi"].target == D("0.20")

    def test_targets_are_editable(self, baseline: DealInputs):
        lenient = replace(
            baseline,
            assumptions=replace(
                baseline.assumptions,
                flip=FlipAssumptions(minimum_net_profit=D("5000"), minimum_roi=D("0.05")),
            ),
        )
        assert analyze_flip(lenient).meets_criteria is True


class TestWarningsAndEdges:
    def test_negative_profit_is_reported_not_hidden(self, baseline: DealInputs):
        bad = replace(baseline, purchase_price=D("230000"))
        result = analyze_flip(bad)
        assert result.profit < 0
        assert any("loses money" in w for w in result.warnings)

    def test_heavy_rehab_relative_to_arv_is_flagged(self, baseline: DealInputs):
        heavy = replace(baseline, rehab=D("120000"))
        assert any("Rehab exceeds 35%" in w for w in analyze_flip(heavy).warnings)

    def test_thin_margin_is_flagged(self, baseline: DealInputs):
        thin = replace(baseline, purchase_price=D("175000"))
        assert any("margin is under 10%" in w for w in analyze_flip(thin).warnings)

    def test_low_arv_can_make_max_price_zero_rather_than_negative(
        self, baseline: DealInputs
    ):
        # ARV barely above rehab: no purchase price works, but the engine must
        # not report a negative maximum offer.
        doomed = replace(baseline, arv=D("60000"), rehab=D("45000"))
        assert analyze_flip(doomed).max_purchase_price >= 0

    def test_zero_rehab_is_valid(self, baseline: DealInputs):
        turnkey = replace(baseline, rehab=D("0"))
        result = analyze_flip(turnkey)
        assert result.viable is True
        assert D(result.detail["costs"]["rehab_total"]) == 0

    @pytest.mark.parametrize("field", ["purchase_price", "arv", "rehab"])
    def test_missing_required_input_is_not_viable(self, baseline: DealInputs, field):
        stripped = replace(baseline, **{field: None})
        if field == "arv":
            stripped = replace(stripped, arv_low=None, arv_high=None)
        if field == "rehab":
            stripped = replace(stripped, rehab_low=None, rehab_high=None)
        result = analyze_flip(stripped)
        assert result.viable is False
        assert field in result.missing_inputs
        assert result.profit is None

    def test_extreme_interest_rate_is_survivable_arithmetic(self, baseline: DealInputs):
        from atlas_financial_engine import FinancingTerms

        loan_shark = replace(
            baseline,
            assumptions=replace(
                baseline.assumptions,
                flip=FlipAssumptions(
                    financing=FinancingTerms(annual_interest_rate=D("0.45"), points=D("0.10"))
                ),
            ),
        )
        result = analyze_flip(loan_shark)
        assert result.viable is True
        assert result.profit < analyze_flip(baseline).profit


class TestRangeInputs:
    def test_arv_range_uses_the_midpoint(self, baseline: DealInputs):
        ranged = replace(baseline, arv=None, arv_low=D("240000"), arv_high=D("260000"))
        assert analyze_flip(ranged).profit == analyze_flip(baseline).profit

    def test_explicit_point_estimate_wins_over_a_range(self, baseline: DealInputs):
        both = replace(baseline, arv=D("250000"), arv_low=D("100000"), arv_high=D("400000"))
        assert D(both.effective_arv) == D("250000")
