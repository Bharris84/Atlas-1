"""Capital efficiency metric.

Two properties matter most: the arithmetic must be reproducible by hand from
the inputs the metric publishes, and efficiency must stay separate from
affordability.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from atlas_financial_engine import (
    InvestorProfile,
    ProfitHorizon,
    Strategy,
    analyze_all_strategies,
    compute_capital_efficiency,
)
from atlas_financial_engine.capital_efficiency import PROVISIONAL_TARGET_RETURN
from atlas_financial_engine.money import D
from atlas_financial_engine.results import StrategyResult


def _result(
    strategy: Strategy = Strategy.FLIP,
    profit="40000",
    cash="20000",
    months=6,
    viable=True,
) -> StrategyResult:
    return StrategyResult(
        strategy=strategy,
        viable=viable,
        profit=D(profit) if profit is not None else None,
        cash_required=D(cash) if cash is not None else None,
        time_to_liquidity_months=months,
    )


class TestArithmetic:
    def test_transactional_return_is_annualised_by_holding_period(self):
        # $40,000 on $20,000 over 6 months = 200% for the period, 400% annualised.
        metric = compute_capital_efficiency(_result())
        assert metric.return_on_capital == D("2.0000")
        assert metric.capital_velocity == D("2.0000")
        assert metric.annualized_return_on_capital == D("4.0000")

    def test_annual_income_is_not_annualised_twice(self):
        """A rental's profit is already a yearly figure."""
        metric = compute_capital_efficiency(
            _result(strategy=Strategy.BUY_HOLD, profit="8000", cash="80000", months=None)
        )
        assert metric.horizon == ProfitHorizon.ANNUAL_INCOME
        assert metric.capital_velocity == D("1.0000")
        assert metric.return_on_capital == D("0.1000")
        assert metric.annualized_return_on_capital == D("0.1000")

    def test_profit_per_thousand_deployed(self):
        metric = compute_capital_efficiency(_result(profit="40000", cash="20000"))
        assert metric.profit_per_1k_deployed == D("2000.00")

    def test_a_longer_hold_lowers_the_annualised_return(self):
        fast = compute_capital_efficiency(_result(months=3))
        slow = compute_capital_efficiency(_result(months=12))
        assert fast.annualized_return_on_capital > slow.annualized_return_on_capital

    def test_more_capital_for_the_same_profit_is_less_efficient(self):
        # Figures chosen below the score cap, so the difference is visible in
        # the score and not just in the underlying return.
        lean = compute_capital_efficiency(_result(profit="3000", cash="20000", months=12))
        heavy = compute_capital_efficiency(_result(profit="3000", cash="80000", months=12))
        assert lean.return_on_capital > heavy.return_on_capital
        assert lean.score > heavy.score

    def test_the_published_inputs_reproduce_the_result_by_hand(self):
        """Transparency is the point: a user must be able to check this."""
        metric = compute_capital_efficiency(_result(profit="30000", cash="25000", months=6))
        profit = D(metric.inputs["profit"])
        capital = D(metric.inputs["capital_deployed"])
        months = D(metric.inputs["horizon_months"])
        assert metric.annualized_return_on_capital == (profit / capital) * (12 / months)


class TestScoring:
    def test_hitting_the_target_scores_fifty(self):
        # 20% annualised against a 20% target.
        metric = compute_capital_efficiency(
            _result(strategy=Strategy.BUY_HOLD, profit="2000", cash="10000", months=None),
            target_return=D("0.20"),
        )
        assert metric.score == D("50.0000")

    def test_twice_the_target_scores_one_hundred(self):
        metric = compute_capital_efficiency(
            _result(strategy=Strategy.BUY_HOLD, profit="4000", cash="10000", months=None),
            target_return=D("0.20"),
        )
        assert metric.score == D("100.0000")

    def test_the_score_is_capped_at_one_hundred(self):
        metric = compute_capital_efficiency(
            _result(strategy=Strategy.BUY_HOLD, profit="90000", cash="10000", months=None),
            target_return=D("0.20"),
        )
        assert metric.score == D("100.0000")

    def test_a_loss_scores_zero(self):
        metric = compute_capital_efficiency(_result(profit="-5000"))
        assert metric.score == 0

    def test_the_investor_target_takes_priority_over_the_deal_target(self):
        profile = InvestorProfile(minimum_roi=D("0.40"))
        metric = compute_capital_efficiency(
            _result(strategy=Strategy.BUY_HOLD, profit="2000", cash="10000", months=None),
            profile=profile,
            target_return=D("0.20"),
        )
        assert metric.score_target == D("0.40")
        assert metric.inputs["target_return_source"] == "investor profile"

    def test_falls_back_to_the_deal_target_then_to_the_engine_default(self):
        with_deal = compute_capital_efficiency(_result(), target_return=D("0.25"))
        assert with_deal.score_target == D("0.25")
        assert with_deal.inputs["target_return_source"] == "deal assumptions"

        bare = compute_capital_efficiency(_result())
        assert bare.score_target == PROVISIONAL_TARGET_RETURN
        assert bare.inputs["target_return_source"] == "Atlas default"


class TestCapitalFreeStrategies:
    def test_a_profitable_no_capital_strategy_scores_full_marks(self):
        """Return on zero capital is undefined, and it is the best case."""
        metric = compute_capital_efficiency(
            _result(strategy=Strategy.WHOLESALE, profit="12000", cash="0", months=1)
        )
        assert metric.capital_free is True
        assert metric.return_on_capital is None
        assert metric.score == D("100.0000")
        assert any("undefined rather than infinite" in n for n in metric.notes)

    def test_a_no_capital_strategy_earning_nothing_scores_zero(self):
        metric = compute_capital_efficiency(
            _result(strategy=Strategy.WHOLESALE, profit="0", cash="0", months=1)
        )
        assert metric.score == 0


class TestAffordabilitySeparateFromEfficiency:
    def test_an_unaffordable_deal_keeps_its_efficiency_score(self):
        """Efficiency and affordability are different problems.

        Collapsing them would hide which one you actually have.
        """
        profile = InvestorProfile(available_capital=D("30000"))
        metric = compute_capital_efficiency(
            _result(profit="40000", cash="80000"), profile=profile
        )
        assert metric.within_capital_limit is False
        assert metric.score > 0
        assert any("funding constraint" in n for n in metric.notes)

    def test_share_of_available_capital_is_reported(self):
        profile = InvestorProfile(available_capital=D("100000"))
        metric = compute_capital_efficiency(_result(cash="25000"), profile=profile)
        assert metric.share_of_available_capital == D("0.2500")

    def test_the_deployment_ceiling_binds_before_total_capital(self):
        profile = InvestorProfile(
            available_capital=D("100000"), max_capital_deployment=D("30000")
        )
        metric = compute_capital_efficiency(_result(cash="50000"), profile=profile)
        assert metric.capital_ceiling == D("30000")
        assert metric.within_capital_limit is False

    def test_without_a_profile_affordability_is_unknown_not_assumed(self):
        metric = compute_capital_efficiency(_result())
        assert metric.within_capital_limit is None
        assert metric.share_of_available_capital is None


class TestNotComputable:
    def test_an_unviable_strategy_reports_that_it_cannot_be_computed(self):
        metric = compute_capital_efficiency(
            _result(viable=False, profit=None, cash=None)
        )
        assert metric.computable is False
        assert metric.score is None
        assert "cannot be computed" in metric.notes[0]

    def test_a_missing_profit_is_not_treated_as_zero(self):
        metric = compute_capital_efficiency(_result(profit=None))
        assert metric.computable is False
        assert metric.score is None


class TestTransparency:
    def test_the_formula_is_stated_in_words(self):
        metric = compute_capital_efficiency(_result())
        assert "annualised return on capital" in metric.formula
        assert "scores 50" in metric.formula

    def test_annualising_a_short_hold_carries_its_caveat(self):
        """A 2x annualisation assumes deal flow that may not exist."""
        metric = compute_capital_efficiency(_result(months=6))
        assert any("redeployed into a comparable deal" in n for n in metric.notes)

    def test_the_origin_of_the_target_is_stated_not_flagged(self):
        """Three different answers — investor, deal, Atlas default — are worth
        distinguishing, so the source is reported rather than reduced to a
        provisional/not boolean."""
        bare = compute_capital_efficiency(_result())
        assert bare.inputs["target_return_source"] == "Atlas default"

        stated = compute_capital_efficiency(
            _result(), profile=InvestorProfile(minimum_roi=D("0.25"))
        )
        assert stated.inputs["target_return_source"] == "investor profile"

        from_deal = compute_capital_efficiency(_result(), target_return=D("0.30"))
        assert from_deal.inputs["target_return_source"] == "deal assumptions"

    def test_serialises_to_json(self):
        import json

        payload = compute_capital_efficiency(_result()).to_dict()
        assert json.loads(json.dumps(payload))["strategy"] == "flip"


class TestIntegration:
    @pytest.fixture
    def comparison(self, baseline):
        return analyze_all_strategies(baseline)

    def test_every_strategy_gets_a_metric(self, comparison):
        assert set(comparison.capital_efficiency) == set(comparison.results)

    def test_the_metric_appears_in_the_serialised_comparison(self, comparison):
        payload = comparison.to_dict()
        assert "capital_efficiency" in payload
        assert payload["capital_efficiency"]["flip"]["formula"]

    def test_the_ranking_uses_the_score_the_user_is_shown(self, baseline):
        """Anti-drift. This is the whole point of the consolidation.

        Atlas previously carried two definitions of capital efficiency: one
        driving the ranking, a different one displayed. They disagreed. There
        is now one, and this asserts the ranking component is that exact value
        for every strategy — not merely close to it.
        """
        comparison = analyze_all_strategies(baseline)
        assert comparison.scores, "expected at least one viable strategy"
        for score in comparison.scores:
            displayed = comparison.capital_efficiency[score.strategy]
            assert score.components["capital_efficiency"] == displayed.score, (
                f"{score.strategy.value}: ranking used "
                f"{score.components['capital_efficiency']} but the UI shows "
                f"{displayed.score}"
            )

    def test_no_second_capital_efficiency_definition_exists(self):
        """Guards against a competing implementation reappearing."""
        from atlas_financial_engine import strategy_engine

        assert not hasattr(strategy_engine, "_capital_efficiency_score")

    def test_the_ranking_score_is_time_adjusted(self, baseline):
        """The old ranking definition ignored holding period. This proves the
        replacement does not: a faster exit must score higher on the same
        profit and capital."""
        from dataclasses import replace as dc_replace

        from atlas_financial_engine import FlipAssumptions

        fast = dc_replace(
            baseline,
            assumptions=dc_replace(
                baseline.assumptions,
                flip=FlipAssumptions(holding_months=3),
            ),
        )
        slow = dc_replace(
            baseline,
            assumptions=dc_replace(
                baseline.assumptions,
                flip=FlipAssumptions(holding_months=12),
            ),
        )
        fast_score = next(
            s for s in analyze_all_strategies(fast).scores if s.strategy == Strategy.FLIP
        )
        slow_score = next(
            s for s in analyze_all_strategies(slow).scores if s.strategy == Strategy.FLIP
        )
        assert (
            fast_score.components["capital_efficiency"]
            > slow_score.components["capital_efficiency"]
        )

    def test_brrrr_reports_how_much_capital_is_recycled(self, baseline):
        metric = analyze_all_strategies(baseline).capital_efficiency[Strategy.BRRRR]
        assert metric.capital_recycled_percent is not None
        assert D("0") <= metric.capital_recycled_percent <= D("1")

    def test_it_is_deterministic(self, baseline):
        import json

        first = json.dumps(analyze_all_strategies(baseline).to_dict()["capital_efficiency"], sort_keys=True)
        second = json.dumps(analyze_all_strategies(baseline).to_dict()["capital_efficiency"], sort_keys=True)
        assert first == second
