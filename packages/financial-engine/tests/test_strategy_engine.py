"""Strategy engine: running every strategy and ranking them honestly.

The behaviour under test that matters most commercially is that the engine does
NOT simply recommend whichever strategy shows the largest gross profit.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from atlas_financial_engine import (
    Confidence,
    DealInputs,
    Strategy,
    StrategyRankingWeights,
    analyze_all_strategies,
    score_strategy,
)
from atlas_financial_engine.money import D


class TestComparison:
    def test_every_strategy_is_evaluated(self, baseline: DealInputs):
        results = analyze_all_strategies(baseline).results
        assert set(results) == {
            Strategy.WHOLESALE,
            Strategy.FLIP,
            Strategy.BUY_HOLD,
            Strategy.BRRRR,
            Strategy.SELLER_FINANCE,
        }

    def test_ranking_is_ordered_by_score(self, baseline: DealInputs):
        scores = analyze_all_strategies(baseline).scores
        assert scores == sorted(scores, key=lambda s: s.score, reverse=True)

    def test_a_recommendation_and_an_alternative_are_produced(self, baseline: DealInputs):
        comparison = analyze_all_strategies(baseline)
        assert comparison.recommended is not None
        assert comparison.alternative is not None
        assert comparison.recommended != comparison.alternative

    def test_rationale_is_produced_and_non_empty(self, baseline: DealInputs):
        assert analyze_all_strategies(baseline).rationale

    def test_overall_confidence_is_the_weakest_link(self, baseline: DealInputs):
        from atlas_financial_engine import Evidence, RehabBasis, RentBasis, ValueBasis

        weak = replace(
            baseline,
            evidence=Evidence(
                arv_basis=ValueBasis.AUTOMATED_VALUATION,
                rehab_basis=RehabBasis.CONTRACTOR_BID,
                rent_basis=RentBasis.LEASE_IN_PLACE,
            ),
        )
        assert analyze_all_strategies(weak).overall_confidence == Confidence.LOW

    def test_viable_exit_count_only_counts_strategies_that_clear_the_buy_box(
        self, baseline: DealInputs
    ):
        comparison = analyze_all_strategies(baseline)
        expected = sum(
            1 for r in comparison.results.values() if r.viable and r.meets_criteria
        )
        assert comparison.viable_exit_count == expected


class TestRankingPhilosophy:
    def test_four_times_the_profit_does_not_automatically_win(
        self, baseline: DealInputs
    ):
        """The headline rule: gross profit alone does not decide the ranking.

        A slow, capital-hungry flip earning $60,000 on $200,000 over a year is
        scored against a $15,000 assignment needing no capital and closing in a
        month. The assignment wins, because capital and time are real costs.
        """
        from atlas_financial_engine.results import StrategyResult

        capital_hungry = StrategyResult(
            strategy=Strategy.FLIP,
            viable=True,
            profit=D("60000"),
            cash_required=D("200000"),
            roi=D("0.30"),
            time_to_liquidity_months=12,
            meets_criteria=True,
            confidence=Confidence.HIGH,
        )
        capital_light = StrategyResult(
            strategy=Strategy.WHOLESALE,
            viable=True,
            profit=D("15000"),
            cash_required=D("0"),
            time_to_liquidity_months=1,
            meets_criteria=True,
            confidence=Confidence.HIGH,
        )
        assert capital_hungry.profit > capital_light.profit * 3
        assert (
            score_strategy(capital_light, baseline).score
            > score_strategy(capital_hungry, baseline).score
        )

    def test_a_no_capital_strategy_is_not_penalised_for_undefined_roi(
        self, baseline: DealInputs
    ):
        """Return on zero cash is undefined, not zero. Scoring it as zero would
        punish a strategy for the very thing that makes it attractive."""
        from atlas_financial_engine.results import StrategyResult

        result = StrategyResult(
            strategy=Strategy.WHOLESALE,
            viable=True,
            profit=D("15000"),
            cash_required=D("0"),
            roi=None,
            time_to_liquidity_months=1,
            meets_criteria=True,
            confidence=Confidence.HIGH,
        )
        assert score_strategy(result, baseline).components["roi"] == D("100")

    def test_a_dominant_deal_still_wins_on_the_merits(self, baseline: DealInputs):
        """The counterweight: de-emphasising profit must not mean ignoring it.

        At this price the flip leads on profit, ROI and capital efficiency at
        once, so it should be recommended.
        """
        deal = replace(baseline, purchase_price=D("95000"))
        comparison = analyze_all_strategies(deal)
        flip = comparison.results[Strategy.FLIP]
        assert flip.profit > comparison.results[Strategy.WHOLESALE].profit
        assert flip.roi > D("1.0")
        assert comparison.recommended == Strategy.FLIP

    def test_capital_efficiency_is_weighted_heavily_by_default(self):
        weights = StrategyRankingWeights()
        assert weights.capital_efficiency >= weights.profit

    def test_weights_are_configurable(self, baseline: DealInputs):
        deal = replace(baseline, purchase_price=D("95000"))
        profit_only = StrategyRankingWeights(
            profit=D("1"),
            capital_efficiency=D("0"),
            roi=D("0"),
            cash_flow=D("0"),
            equity_creation=D("0"),
            time_to_liquidity=D("0"),
            risk=D("0"),
        )
        comparison = analyze_all_strategies(deal)
        rescored = sorted(
            (
                score_strategy(r, deal, profit_only)
                for r in comparison.results.values()
                if r.viable
            ),
            key=lambda s: s.score,
            reverse=True,
        )
        # Scoring purely on profit changes the answer, which is the point of
        # making the weights configurable.
        assert rescored[0].strategy != comparison.recommended

    def test_missing_the_buy_box_costs_score_but_does_not_disqualify(
        self, baseline: DealInputs
    ):
        comparison = analyze_all_strategies(baseline)
        missed = [s for s in comparison.scores if not s.meets_criteria]
        assert missed
        assert all(s.penalty_applied > 0 for s in missed)
        assert all(s.score >= 0 for s in comparison.scores)

    def test_zero_cash_with_zero_profit_is_not_perfect_efficiency(
        self, baseline: DealInputs
    ):
        """A wholesale with no spread commits no capital, but earns nothing."""
        overpriced = replace(baseline, purchase_price=D("240000"))
        comparison = analyze_all_strategies(overpriced)
        wholesale_score = next(
            s for s in comparison.scores if s.strategy == Strategy.WHOLESALE
        )
        assert wholesale_score.components["capital_efficiency"] == 0

    def test_negative_cash_flow_hold_scores_zero_on_profit(self, baseline: DealInputs):
        strained = replace(baseline, purchase_price=D("300000"))
        comparison = analyze_all_strategies(strained)
        score = next(s for s in comparison.scores if s.strategy == Strategy.BUY_HOLD)
        assert comparison.results[Strategy.BUY_HOLD].monthly_cash_flow < 0
        assert score.components["profit"] == 0

    def test_scores_stay_within_bounds(self, baseline: DealInputs):
        for score in analyze_all_strategies(baseline).scores:
            assert D("0") <= score.score <= D("100")
            for value in score.components.values():
                assert D("0") <= value <= D("100")


class TestPartialInformation:
    def test_engine_still_runs_with_only_price_and_rent(self, baseline: DealInputs):
        """No ARV and no rehab: rentals still underwrite, deal models cannot."""
        sparse = replace(
            baseline,
            arv=None,
            arv_low=None,
            arv_high=None,
            rehab=None,
            rehab_low=None,
            rehab_high=None,
        )
        comparison = analyze_all_strategies(sparse)
        assert comparison.results[Strategy.BUY_HOLD].viable is True
        assert comparison.results[Strategy.FLIP].viable is False
        assert comparison.results[Strategy.WHOLESALE].viable is False
        assert comparison.recommended in (Strategy.BUY_HOLD, Strategy.SELLER_FINANCE)

    def test_missing_information_is_collected_and_deduplicated(
        self, baseline: DealInputs
    ):
        sparse = replace(baseline, arv=None, arv_low=None, arv_high=None)
        missing = analyze_all_strategies(sparse).missing_information
        assert "arv" in missing
        assert len(missing) == len(set(missing))

    def test_no_recommendation_when_nothing_can_be_evaluated(self, baseline: DealInputs):
        empty = DealInputs(assumptions=baseline.assumptions)
        comparison = analyze_all_strategies(empty)
        assert comparison.recommended is None
        assert all(not r.viable for r in comparison.results.values())
        assert "No strategy could be evaluated" in comparison.rationale[0]

    def test_unviable_strategies_carry_a_stated_reason(self, baseline: DealInputs):
        empty = DealInputs(assumptions=baseline.assumptions)
        for result in analyze_all_strategies(empty).results.values():
            assert result.not_viable_reason
            assert result.missing_inputs


class TestSerialization:
    def test_comparison_serialises_to_json_safe_primitives(self, baseline: DealInputs):
        import json

        payload = analyze_all_strategies(baseline).to_dict()
        # Must round-trip through JSON: this is what crosses the API boundary.
        assert json.loads(json.dumps(payload))["recommended_strategy"] is not None

    def test_money_is_serialised_as_string_not_float(self, baseline: DealInputs):
        payload = analyze_all_strategies(baseline).to_dict()
        assert isinstance(payload["strategies"]["flip"]["profit"], str)
