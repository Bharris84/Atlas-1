"""Calibration.

The method under test: substitute known actual values into the prediction one
at a time, and report how far each moves the answer. What survives correcting
every input is model error, not estimate error — and that distinction is the
whole reason this exists.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from atlas_financial_engine import (
    ActualOutcome,
    Assumptions,
    DealInputs,
    HoldingCosts,
    RentalAssumptions,
    Strategy,
    build_report,
    calibrate_deal,
    calibrate_from_dicts,
)
from atlas_financial_engine.money import D


@pytest.fixture
def deal() -> DealInputs:
    return DealInputs(
        purchase_price=D("150000"),
        arv=D("250000"),
        rehab=D("45000"),
        monthly_rent=D("1800"),
        assumptions=Assumptions(
            holding=HoldingCosts(annual_taxes=D("2400"), annual_insurance=D("1800")),
            rental=RentalAssumptions(annual_taxes=D("2400"), annual_insurance=D("1800")),
        ),
    )


def _flip_outcome(**overrides) -> ActualOutcome:
    base = dict(strategy_executed=Strategy.FLIP, actual_profit=D("20000"))
    base.update(overrides)
    return ActualOutcome(**base)


class TestBasicComparison:
    def test_reports_prediction_actual_and_difference(self, deal):
        result = calibrate_deal("Test deal", deal, _flip_outcome())
        assert result.predicted_profit is not None
        assert result.actual_profit == D("20000")
        assert result.difference == D("20000") - result.predicted_profit

    def test_difference_is_positive_when_reality_beat_the_prediction(self, deal):
        result = calibrate_deal("Test", deal, _flip_outcome(actual_profit=D("60000")))
        assert result.difference > 0

    def test_difference_percent_is_relative_to_the_prediction(self, deal):
        result = calibrate_deal("Test", deal, _flip_outcome())
        expected = result.difference / abs(result.predicted_profit)
        assert abs(result.difference_percent - expected) < D("0.0001")

    def test_states_what_basis_the_profit_is_on(self, deal):
        """An exit profit and an annual cash flow are not comparable figures."""
        flip = calibrate_deal("F", deal, _flip_outcome())
        hold = calibrate_deal(
            "H",
            deal,
            ActualOutcome(strategy_executed=Strategy.BUY_HOLD, actual_profit=D("4000")),
        )
        assert "exit" in flip.profit_basis
        assert "annual cash flow" in hold.profit_basis

    def test_an_unanalysable_deal_reports_no_prediction(self):
        bare = DealInputs(purchase_price=D("100000"))  # no ARV or rehab
        result = calibrate_deal("Bare", bare, _flip_outcome())
        assert result.predicted_profit is None
        assert result.difference is None
        assert "could not underwrite" in result.notes[0]


class TestAttribution:
    def test_a_wrong_arv_is_attributed_to_the_arv(self, deal):
        # Sold for $30,000 less than predicted.
        result = calibrate_deal(
            "ARV miss", deal, _flip_outcome(actual_sale_price=D("220000"))
        )
        arv = next(a for a in result.attributions if a.factor == "arv")
        assert arv.predicted_value == "250000"
        assert arv.actual_value == "220000"
        # Lower sale price reduces profit, and by less than the full $30,000
        # because the selling costs fall with it.
        assert arv.profit_impact < 0
        assert arv.profit_impact > D("-30000")

    def test_a_rehab_overrun_is_attributed_to_the_rehab(self, deal):
        result = calibrate_deal(
            "Rehab overrun", deal, _flip_outcome(actual_rehab=D("70000"))
        )
        rehab = next(a for a in result.attributions if a.factor == "rehab")
        assert rehab.profit_impact < 0

    def test_a_longer_hold_costs_money(self, deal):
        result = calibrate_deal(
            "Slow sale", deal, _flip_outcome(actual_holding_months=12)
        )
        holding = next(a for a in result.attributions if a.factor == "holding_months")
        assert holding.predicted_value == "6"
        assert holding.actual_value == "12"
        assert holding.profit_impact < 0

    def test_the_dominant_factor_is_the_largest_mover(self, deal):
        result = calibrate_deal(
            "Both wrong",
            deal,
            _flip_outcome(actual_sale_price=D("200000"), actual_rehab=D("48000")),
        )
        assert result.dominant_factor == "ARV / sale price"

    def test_attributions_are_ordered_by_magnitude(self, deal):
        result = calibrate_deal(
            "Multi",
            deal,
            _flip_outcome(
                actual_sale_price=D("210000"),
                actual_rehab=D("52000"),
                actual_holding_months=8,
            ),
        )
        impacts = [abs(a.profit_impact) for a in result.attributions]
        assert impacts == sorted(impacts, reverse=True)

    def test_only_supplied_actuals_are_attributed(self, deal):
        result = calibrate_deal("Partial", deal, _flip_outcome(actual_rehab=D("50000")))
        assert {a.factor for a in result.attributions} == {"rehab"}

    def test_no_actuals_means_no_attribution_and_says_so(self, deal):
        result = calibrate_deal("None", deal, _flip_outcome())
        assert result.attributions == []
        assert any("cannot be attributed" in n for n in result.notes)

    def test_an_input_that_was_right_moves_nothing(self, deal):
        result = calibrate_deal(
            "Correct ARV", deal, _flip_outcome(actual_sale_price=D("250000"))
        )
        arv = next(a for a in result.attributions if a.factor == "arv")
        assert arv.profit_impact == 0


class TestResidual:
    def test_perfect_inputs_and_a_perfect_model_leave_no_residual(self, deal):
        """If Atlas predicted it exactly, the residual is zero."""
        predicted = calibrate_deal("X", deal, _flip_outcome()).predicted_profit
        result = calibrate_deal("Exact", deal, _flip_outcome(actual_profit=predicted))
        assert result.unexplained_residual == 0

    def test_a_missing_cost_shows_up_as_a_residual_not_an_attribution(self, deal):
        """The signal that the cost model itself is wrong.

        Every input is corrected, yet reality still came in $8,000 lower — so
        the gap is a cost Atlas is not charging.
        """
        with_actuals = calibrate_deal(
            "Setup", deal, _flip_outcome(actual_sale_price=D("235000"))
        ).profit_with_actual_inputs
        result = calibrate_deal(
            "Hidden cost",
            deal,
            _flip_outcome(
                actual_sale_price=D("235000"),
                actual_profit=with_actuals - D("8000"),
            ),
        )
        assert result.unexplained_residual == D("-8000.00")
        assert any("cost model" in n for n in result.notes)

    def test_explained_plus_residual_reconciles_to_the_total_gap(self, deal):
        result = calibrate_deal(
            "Reconcile",
            deal,
            _flip_outcome(actual_sale_price=D("230000"), actual_rehab=D("55000")),
        )
        assert (
            result.explained_by_inputs + result.unexplained_residual == result.difference
        )

    def test_interaction_is_reported_rather_than_hidden(self, deal):
        """One-at-a-time impacts need not sum to the total; say so."""
        result = calibrate_deal(
            "Interaction",
            deal,
            _flip_outcome(actual_sale_price=D("210000"), actual_rehab=D("60000")),
        )
        summed = sum(a.profit_impact for a in result.attributions)
        assert result.explained_by_inputs - summed == result.interaction_effect


class TestReport:
    def _results(self, deal, outcomes):
        return [
            calibrate_deal(f"Deal {i}", deal, outcome)
            for i, outcome in enumerate(outcomes, start=1)
        ]

    def test_mean_absolute_error_is_reported(self, deal):
        report = build_report(
            self._results(deal, [_flip_outcome(actual_profit=D("20000"))])
        )
        assert report.mean_absolute_error is not None

    def test_a_consistent_direction_is_called_a_bias(self, deal):
        predicted = calibrate_deal("X", deal, _flip_outcome()).predicted_profit
        # Every deal came in below prediction, by a lot.
        outcomes = [
            _flip_outcome(actual_profit=predicted - D("12000")),
            _flip_outcome(actual_profit=predicted - D("15000")),
            _flip_outcome(actual_profit=predicted - D("9000")),
        ]
        report = build_report(self._results(deal, outcomes))
        assert report.mean_signed_error < 0
        assert any("overstates profit" in n for n in report.notes)

    def test_a_small_sample_is_labelled_as_such(self, deal):
        report = build_report(self._results(deal, [_flip_outcome()]))
        assert any("not evidence" in n for n in report.notes)

    def test_eight_deals_still_warns_about_sample_size(self, deal):
        report = build_report(self._results(deal, [_flip_outcome()] * 8))
        assert any("provisional" in n for n in report.notes)

    def test_dominant_factors_are_counted_across_deals(self, deal):
        outcomes = [
            _flip_outcome(actual_sale_price=D("210000")),
            _flip_outcome(actual_sale_price=D("215000")),
        ]
        report = build_report(self._results(deal, outcomes))
        assert report.dominant_factor_counts["ARV / sale price"] == 2

    def test_report_serialises_to_json(self, deal):
        import json

        report = build_report(self._results(deal, [_flip_outcome()]))
        assert json.loads(json.dumps(report.to_dict()))["deal_count"] == 1


class TestDictInterface:
    def test_runs_from_plain_dictionaries(self):
        report = calibrate_from_dicts(
            [
                {
                    "name": "From dict",
                    "inputs": {
                        "purchase_price": "150000",
                        "arv": "250000",
                        "rehab": "45000",
                        "monthly_rent": "1800",
                    },
                    "actual": {
                        "strategy_executed": "flip",
                        "actual_profit": "18000",
                        "actual_sale_price": "235000",
                    },
                }
            ]
        )
        assert len(report.results) == 1
        assert report.results[0].name == "From dict"
        assert report.results[0].dominant_factor == "ARV / sale price"

    def test_is_deterministic(self):
        import json

        deals = [
            {
                "name": "D",
                "inputs": {"purchase_price": "150000", "arv": "250000", "rehab": "45000"},
                "actual": {"strategy_executed": "flip", "actual_profit": "18000"},
            }
        ]
        first = json.dumps(calibrate_from_dicts(deals).to_dict(), sort_keys=True)
        second = json.dumps(calibrate_from_dicts(deals).to_dict(), sort_keys=True)
        assert first == second
