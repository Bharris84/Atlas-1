"""Edge cases, determinism, and assumption round-tripping.

An analysis saved today must produce the same numbers when reopened next year.
That property is what makes an audit trail meaningful, so it is tested rather
than assumed.
"""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal

import pytest

from atlas_financial_engine import (
    Assumptions,
    DealInputs,
    FinancingTerms,
    FlipAssumptions,
    RentalAssumptions,
    Strategy,
    analyze_all_strategies,
    analyze_buy_hold,
    analyze_flip,
    build_inputs,
)
from atlas_financial_engine.money import D


class TestDeterminism:
    def test_identical_inputs_produce_byte_identical_output(self, baseline: DealInputs):
        first = json.dumps(analyze_all_strategies(baseline).to_dict(), sort_keys=True)
        second = json.dumps(analyze_all_strategies(baseline).to_dict(), sort_keys=True)
        assert first == second

    def test_repeated_runs_are_stable_across_many_iterations(self, baseline: DealInputs):
        reference = analyze_flip(baseline).profit
        assert all(analyze_flip(baseline).profit == reference for _ in range(25))

    def test_no_floating_point_contamination(self, baseline: DealInputs):
        """Every published number must be a Decimal, never a float."""
        payload = analyze_all_strategies(baseline).to_dict()

        def walk(node):
            if isinstance(node, float):
                raise AssertionError(f"float leaked into output: {node}")
            if isinstance(node, dict):
                for value in node.values():
                    walk(value)
            if isinstance(node, list):
                for value in node:
                    walk(value)

        walk(payload)

    def test_inputs_round_trip_through_serialisation(self, baseline: DealInputs):
        restored = DealInputs.from_dict(baseline.to_dict())
        assert analyze_flip(restored).profit == analyze_flip(baseline).profit

    def test_analysis_is_reproducible_from_stored_assumptions(self, baseline: DealInputs):
        """Reopening a saved analysis must reproduce it exactly."""
        stored = json.loads(json.dumps(baseline.to_dict()))
        assert (
            analyze_all_strategies(DealInputs.from_dict(stored)).to_dict()
            == analyze_all_strategies(baseline).to_dict()
        )


class TestAssumptionRoundTrip:
    def test_defaults_survive_a_round_trip(self):
        restored = Assumptions.from_dict(Assumptions().to_dict())
        assert restored == Assumptions()

    def test_overrides_survive_a_round_trip(self):
        custom = Assumptions(
            flip=FlipAssumptions(minimum_net_profit=D("42000"), rehab_contingency=D("0.25"))
        )
        restored = Assumptions.from_dict(custom.to_dict())
        assert restored.flip.minimum_net_profit == D("42000")
        assert restored.flip.rehab_contingency == D("0.25")

    def test_nested_financing_terms_survive_a_round_trip(self):
        custom = Assumptions(
            flip=FlipAssumptions(
                financing=FinancingTerms(annual_interest_rate=D("0.135"), points=D("0.03"))
            )
        )
        restored = Assumptions.from_dict(custom.to_dict())
        assert restored.flip.financing.annual_interest_rate == D("0.135")
        assert restored.flip.financing.points == D("0.03")

    def test_partial_input_falls_back_to_defaults(self):
        """A stored analysis from an older schema must still load."""
        restored = Assumptions.from_dict({"flip": {"minimum_net_profit": "50000"}})
        assert restored.flip.minimum_net_profit == D("50000")
        assert restored.flip.rehab_contingency == D("0.15")
        assert restored.rental.vacancy_percent == D("0.05")

    def test_unknown_keys_are_ignored_rather_than_fatal(self):
        restored = Assumptions.from_dict({"flip": {"a_field_from_the_future": 1}})
        assert restored.flip == FlipAssumptions()

    def test_none_assumptions_yields_defaults(self):
        assert Assumptions.from_dict(None) == Assumptions()

    def test_optional_balloon_survives_a_none_round_trip(self):
        custom = Assumptions.from_dict({"seller_finance": {"balloon_years": None}})
        assert custom.seller_finance.balloon_years is None


class TestZeroAndNegative:
    def test_zero_purchase_price_is_analysable(self, baseline: DealInputs):
        """An inherited or donated property is a real, if unusual, input."""
        free = replace(baseline, purchase_price=D("0"))
        assert analyze_flip(free).viable is True

    def test_zero_arv_produces_a_loss_not_a_crash(self, baseline: DealInputs):
        worthless = replace(baseline, arv=D("0"))
        assert analyze_flip(worthless).profit < 0

    def test_zero_rent_yields_negative_cash_flow(self, baseline: DealInputs):
        assert analyze_buy_hold(replace(baseline, monthly_rent=D("0"))).annual_cash_flow < 0

    def test_everything_zero_does_not_divide_by_zero(self):
        result = analyze_buy_hold(
            DealInputs(
                purchase_price=D("0"),
                monthly_rent=D("0"),
                assumptions=Assumptions(rental=RentalAssumptions(financing=FinancingTerms())),
            )
        )
        assert result.viable is True
        assert result.cap_rate is None  # undefined, not zero
        assert result.dscr is None

    def test_completely_empty_inputs_never_raise(self):
        comparison = analyze_all_strategies(DealInputs())
        assert comparison.recommended is None
        assert all(not r.viable for r in comparison.results.values())


class TestExtremeValues:
    def test_extreme_interest_rate(self, baseline: DealInputs):
        brutal = replace(
            baseline,
            assumptions=replace(
                baseline.assumptions,
                flip=FlipAssumptions(
                    financing=FinancingTerms(annual_interest_rate=D("0.99"))
                ),
            ),
        )
        assert analyze_flip(brutal).profit < analyze_flip(baseline).profit

    def test_zero_interest_rate(self, baseline: DealInputs):
        free_money = replace(
            baseline,
            assumptions=replace(
                baseline.assumptions,
                flip=FlipAssumptions(
                    financing=FinancingTerms(annual_interest_rate=D("0"), points=D("0"))
                ),
            ),
        )
        assert analyze_flip(free_money).profit > analyze_flip(baseline).profit

    def test_rehab_larger_than_arv(self, baseline: DealInputs):
        """A teardown. The engine must report the loss, not refuse the input."""
        teardown = replace(baseline, rehab=D("400000"))
        result = analyze_flip(teardown)
        assert result.profit < 0
        assert result.warnings

    def test_very_large_values_stay_precise(self, baseline: DealInputs):
        """Decimal arithmetic must not drift on eight-figure deals."""
        big = replace(
            baseline,
            purchase_price=D("12000000"),
            arv=D("20000000"),
            rehab=D("3000000"),
        )
        result = analyze_flip(big)
        costs = result.detail["costs"]
        assert result.profit == D("20000000") - D(costs["total_project_cost"])

    def test_fractional_cents_are_rounded_not_truncated(self):
        result = analyze_flip(
            build_inputs(
                purchase_price="100000.333",
                arv="200000.777",
                rehab="20000.555",
                monthly_rent="1500",
            )
        )
        assert result.profit == result.profit.quantize(D("0.01"))


class TestPartialData:
    def test_range_only_inputs_are_usable(self, baseline: DealInputs):
        ranged = replace(
            baseline,
            arv=None,
            arv_low=D("240000"),
            arv_high=D("260000"),
            rehab=None,
            rehab_low=D("40000"),
            rehab_high=D("50000"),
        )
        assert analyze_flip(ranged).profit == analyze_flip(baseline).profit

    def test_single_sided_range_is_used_rather_than_discarded(self, baseline: DealInputs):
        one_sided = replace(baseline, arv=None, arv_low=D("250000"), arv_high=None)
        assert one_sided.effective_arv == D("250000")

    def test_missing_fields_are_reported_for_the_ui(self):
        missing = build_inputs(purchase_price="150000").missing_fields()
        assert "arv" in missing
        assert "rehab" in missing
        assert "monthly_rent" in missing

    def test_zero_taxes_are_reported_as_missing_information(self):
        """Zero is not a tax bill; it is an unanswered question."""
        assert "annual_taxes" in build_inputs(purchase_price="150000").missing_fields()

    def test_engine_works_with_no_external_data_provider(self):
        """Manual entry alone must be enough to produce a full analysis."""
        manual = build_inputs(
            purchase_price="150000", arv="250000", rehab="45000", monthly_rent="1800"
        )
        comparison = analyze_all_strategies(manual)
        assert comparison.recommended is not None
        assert all(
            comparison.results[s].viable
            for s in (Strategy.WHOLESALE, Strategy.FLIP, Strategy.BUY_HOLD)
        )


class TestBuildInputs:
    def test_accepts_loose_numeric_types(self):
        inputs = build_inputs(purchase_price=150000, arv="250000.00", rehab=45000.50)
        assert inputs.purchase_price == D("150000")
        assert inputs.rehab == D("45000.50")

    def test_accepts_formatted_strings(self):
        assert build_inputs(purchase_price="$150,000").purchase_price == D("150000")
