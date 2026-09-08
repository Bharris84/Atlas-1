"""BRRRR model.

The decisive number is cash left in the deal, so most of these tests are about
whether the refinance actually recycles the capital.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from atlas_financial_engine import BrrrrAssumptions, DealInputs, analyze_brrrr
from atlas_financial_engine.money import D


class TestRefinance:
    def test_new_loan_is_ltv_times_post_rehab_value(self, baseline: DealInputs):
        d = analyze_brrrr(baseline).detail
        assert D(d["refinance_loan"]) == D("250000") * D("0.75")

    def test_cash_returned_is_new_loan_less_costs_and_payoff(self, baseline: DealInputs):
        d = analyze_brrrr(baseline).detail
        assert D(d["cash_returned"]) == (
            D(d["refinance_loan"])
            - D(d["refinance_costs"])
            - D(d["acquisition_loan_payoff"])
        )

    def test_cash_left_is_invested_less_returned(self, baseline: DealInputs):
        d = analyze_brrrr(baseline).detail
        assert D(d["cash_left_in_deal"]) == D(d["cash_invested"]) - D(d["cash_returned"])

    def test_equity_after_refinance_reflects_the_ltv(self, baseline: DealInputs):
        d = analyze_brrrr(baseline).detail
        assert D(d["equity_percent"]) == D("0.2500")  # 1 - 75% LTV

    def test_equity_created_is_value_less_all_in_basis(self, baseline: DealInputs):
        d = analyze_brrrr(baseline).detail
        assert D(d["equity_created"]) == D("250000") - D(d["costs"]["total_basis"])

    def test_higher_ltv_returns_more_cash(self, baseline: DealInputs):
        aggressive = replace(
            baseline,
            assumptions=replace(
                baseline.assumptions, brrrr=BrrrrAssumptions(refinance_ltv=D("0.80"))
            ),
        )
        assert D(analyze_brrrr(aggressive).detail["cash_left_in_deal"]) < D(
            analyze_brrrr(baseline).detail["cash_left_in_deal"]
        )

    def test_no_selling_costs_are_charged(self, baseline: DealInputs):
        """A BRRRR refinances rather than sells; there is no commission."""
        assert D(analyze_brrrr(baseline).detail["costs"]["selling_costs"]) == 0


class TestCapitalRecycling:
    def test_a_strong_buy_returns_all_capital(self, baseline: DealInputs):
        great = replace(baseline, purchase_price=D("95000"))
        result = analyze_brrrr(great)
        assert D(result.detail["cash_left_in_deal"]) <= 0
        assert result.cash_required == 0

    def test_undefined_cash_on_cash_when_no_cash_remains(self, baseline: DealInputs):
        """Infinite return is not a number. It is reported as undefined."""
        great = replace(baseline, purchase_price=D("95000"))
        result = analyze_brrrr(great)
        assert result.cash_on_cash is None
        assert any("undefined" in w for w in result.warnings)

    def test_trapped_capital_over_the_ceiling_is_flagged(self, baseline: DealInputs):
        expensive = replace(baseline, purchase_price=D("190000"))
        result = analyze_brrrr(expensive)
        assert D(result.detail["cash_left_in_deal"]) > D("25000")
        assert any("trapped" in w for w in result.warnings)

    def test_buying_at_max_price_meets_the_cash_left_ceiling(self, baseline: DealInputs):
        max_price = analyze_brrrr(baseline).max_purchase_price
        at_max = analyze_brrrr(replace(baseline, purchase_price=max_price))
        cash_left = D(at_max.detail["cash_left_in_deal"])
        assert abs(cash_left - D("25000")) < D("1.00")

    def test_reported_cash_required_is_capital_left_in_the_deal(
        self, baseline: DealInputs
    ):
        """For ranking, BRRRR's capital cost is what stays trapped after refi."""
        result = analyze_brrrr(baseline)
        assert result.cash_required == D(result.detail["cash_left_in_deal"])


class TestProfitSemantics:
    def test_profit_is_realised_cash_flow_not_paper_equity(self, baseline: DealInputs):
        """Equity created is real but unrealised; counting it as profit would
        double-count it against a flip that actually converts it to cash."""
        result = analyze_brrrr(baseline)
        assert result.profit == result.annual_cash_flow
        assert result.equity_created != result.profit

    def test_without_rent_cash_flow_is_unknown_but_equity_still_computes(
        self, baseline: DealInputs
    ):
        no_rent = replace(baseline, monthly_rent=None)
        result = analyze_brrrr(no_rent)
        assert result.viable is True
        assert result.monthly_cash_flow is None
        assert result.dscr is None
        assert result.equity_created is not None
        assert any("No rent estimate" in w for w in result.warnings)


class TestConfidenceAndWarnings:
    def test_non_high_arv_confidence_warns_about_the_appraisal(
        self, baseline: DealInputs
    ):
        from atlas_financial_engine import Evidence, RehabBasis, RentBasis, ValueBasis

        weak = replace(
            baseline,
            evidence=Evidence(
                arv_basis=ValueBasis.AUTOMATED_VALUATION,
                rehab_basis=RehabBasis.CONTRACTOR_BID,
                rent_basis=RentBasis.RENTAL_COMPS,
            ),
        )
        assert any("appraiser" in w for w in analyze_brrrr(weak).warnings)

    @pytest.mark.parametrize("field", ["purchase_price", "arv", "rehab"])
    def test_missing_required_input_is_not_viable(self, baseline: DealInputs, field):
        stripped = replace(baseline, **{field: None})
        if field == "arv":
            stripped = replace(stripped, arv_low=None, arv_high=None)
        if field == "rehab":
            stripped = replace(stripped, rehab_low=None, rehab_high=None)
        result = analyze_brrrr(stripped)
        assert result.viable is False
        assert field in result.missing_inputs

    def test_low_arv_leaves_capital_stranded(self, baseline: DealInputs):
        """When the rehab does not create value, BRRRR fails on its own terms."""
        no_lift = replace(baseline, arv=D("160000"))
        result = analyze_brrrr(no_lift)
        assert D(result.detail["cash_left_in_deal"]) > D("25000")
        assert result.meets_criteria is False
