"""Wholesale model.

The central claim of this model is that it prices the END BUYER's deal rather
than applying a rule of thumb. The round-trip tests below prove that claim:
if the buyer bought at our computed maximum, the flip model must independently
report exactly the profit the buyer required.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from atlas_financial_engine import (
    Assumptions,
    DealInputs,
    FlipAssumptions,
    Strategy,
    WholesaleAssumptions,
    analyze_flip,
    analyze_wholesale,
)
from atlas_financial_engine.money import D


def _detail(result):
    return result.detail


class TestBuyerDrivenPricing:
    def test_max_buyer_price_gives_the_buyer_exactly_their_target_profit(
        self, baseline: DealInputs
    ):
        """Round-trip: re-underwrite the buyer's flip at our computed maximum."""
        wholesale = analyze_wholesale(baseline)
        max_buyer_price = D(_detail(wholesale)["max_buyer_purchase_price"])
        target = D(_detail(wholesale)["buyer_profit_target"])

        w = baseline.assumptions.wholesale
        buyer_view = replace(
            baseline,
            purchase_price=max_buyer_price,
            assumptions=replace(
                baseline.assumptions,
                flip=FlipAssumptions(
                    rehab_contingency=w.buyer_rehab_contingency,
                    holding_months=w.buyer_holding_months,
                    financing=w.buyer_financing,
                ),
            ),
        )
        assert abs(analyze_flip(buyer_view).profit - target) < D("1.00")

    def test_contract_price_leaves_room_for_fee_and_buffer(self, baseline: DealInputs):
        d = _detail(analyze_wholesale(baseline))
        gap = D(d["max_buyer_purchase_price"]) - D(d["max_allowable_contract_price"])
        expected = D(d["target_assignment_fee"]) + D(d["risk_buffer"])
        assert abs(gap - expected) < D("0.02")

    def test_contracting_at_the_maximum_yields_exactly_the_target_fee(
        self, baseline: DealInputs
    ):
        max_contract = analyze_wholesale(baseline).max_purchase_price
        at_max = analyze_wholesale(replace(baseline, purchase_price=max_contract))
        assert abs(
            at_max.profit - baseline.assumptions.wholesale.target_assignment_fee
        ) < D("1.00")
        assert at_max.meets_criteria is True

    def test_does_not_reduce_to_the_seventy_percent_rule(self, baseline: DealInputs):
        """The 70% rule is an approximation Atlas deliberately does not use."""
        rule_of_thumb = D("250000") * D("0.70") - D("45000")
        computed = analyze_wholesale(baseline).max_purchase_price
        assert abs(computed - rule_of_thumb) > D("5000")


class TestAssignmentEconomics:
    def test_no_spread_produces_no_fee_never_a_negative_one(self, baseline: DealInputs):
        overpriced = replace(baseline, purchase_price=D("240000"))
        result = analyze_wholesale(overpriced)
        assert result.profit == 0
        assert result.meets_criteria is False
        assert any("no spread" in w.lower() for w in result.warnings)

    def test_wholesale_is_capital_light(self, baseline: DealInputs):
        assert analyze_wholesale(baseline).cash_required == 0

    def test_transaction_costs_reduce_profit(self, baseline: DealInputs):
        priced_to_win = replace(baseline, purchase_price=D("90000"))
        base = analyze_wholesale(priced_to_win)
        with_costs = analyze_wholesale(
            replace(
                priced_to_win,
                assumptions=replace(
                    priced_to_win.assumptions,
                    wholesale=WholesaleAssumptions(wholesale_transaction_costs=D("2500")),
                ),
            )
        )
        assert base.profit - with_costs.profit == D("2500.00")

    def test_time_to_liquidity_is_fastest_of_all_strategies(self, baseline: DealInputs):
        assert analyze_wholesale(baseline).time_to_liquidity_months == 1


class TestConfigurability:
    def test_higher_buyer_profit_target_lowers_our_maximum(self, baseline: DealInputs):
        greedy_buyer = replace(
            baseline,
            assumptions=replace(
                baseline.assumptions,
                wholesale=WholesaleAssumptions(buyer_profit_percent_of_arv=D("0.25")),
            ),
        )
        assert (
            analyze_wholesale(greedy_buyer).max_purchase_price
            < analyze_wholesale(baseline).max_purchase_price
        )

    def test_larger_assignment_fee_lowers_our_maximum_dollar_for_dollar(
        self, baseline: DealInputs
    ):
        richer = replace(
            baseline,
            assumptions=replace(
                baseline.assumptions,
                wholesale=WholesaleAssumptions(target_assignment_fee=D("25000")),
            ),
        )
        delta = (
            analyze_wholesale(baseline).max_purchase_price
            - analyze_wholesale(richer).max_purchase_price
        )
        assert abs(delta - D("15000")) < D("0.02")

    def test_buyer_profit_floor_binds_on_low_priced_property(self, baseline: DealInputs):
        """On a cheap house, 15% of ARV is less than any investor will work for."""
        cheap = replace(baseline, arv=D("80000"), rehab=D("15000"), purchase_price=D("30000"))
        detail = _detail(analyze_wholesale(cheap))
        # 15% of $80,000 = $12,000, below the $20,000 floor.
        assert D(detail["buyer_profit_target"]) == D("20000.00")

    def test_zero_risk_buffer_is_permitted(self, baseline: DealInputs):
        no_buffer = replace(
            baseline,
            assumptions=replace(
                baseline.assumptions,
                wholesale=WholesaleAssumptions(
                    risk_buffer_percent_of_arv=D("0"), risk_buffer_flat=D("0")
                ),
            ),
        )
        assert D(_detail(analyze_wholesale(no_buffer))["risk_buffer"]) == 0


class TestMissingInputs:
    def test_cannot_underwrite_without_arv(self, baseline: DealInputs):
        result = analyze_wholesale(replace(baseline, arv=None, arv_low=None, arv_high=None))
        assert result.viable is False
        assert "arv" in result.missing_inputs

    def test_cannot_underwrite_without_rehab(self, baseline: DealInputs):
        result = analyze_wholesale(
            replace(baseline, rehab=None, rehab_low=None, rehab_high=None)
        )
        assert result.viable is False
        assert "rehab" in result.missing_inputs

    def test_works_without_a_contract_price(self, baseline: DealInputs):
        """Before making an offer, the maximum allowable offer is the answer."""
        result = analyze_wholesale(replace(baseline, purchase_price=None))
        assert result.viable is True
        assert result.max_purchase_price is not None
        assert result.profit is None
        assert any("no contract price" in w.lower() for w in result.warnings)
