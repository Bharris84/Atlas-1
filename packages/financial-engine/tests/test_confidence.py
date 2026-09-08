"""Confidence engine.

The rule Atlas is enforcing here: never create false precision. A number with
weak support must be labelled as such, every time, with a stated reason.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from atlas_financial_engine import (
    Assertion,
    Confidence,
    Evidence,
    RehabBasis,
    RentBasis,
    ValueBasis,
    assess_arv,
    assess_rehab,
    assess_rent,
)
from atlas_financial_engine.confidence import range_is_wide
from atlas_financial_engine.money import D


def _comps(count: int, similarity="0.85", age_days=90) -> Evidence:
    return Evidence(
        arv_basis=ValueBasis.COMPARABLE_SALES,
        comp_count=count,
        average_comp_similarity=D(similarity),
        average_comp_age_days=age_days,
    )


class TestArvConfidence:
    def test_five_strong_recent_comps_are_high(self):
        assert assess_arv(_comps(5)).level == Confidence.HIGH

    def test_two_weak_comps_are_medium(self):
        assert assess_arv(_comps(2)).level == Confidence.MEDIUM

    def test_one_comp_is_low(self):
        assert assess_arv(_comps(1)).level == Confidence.LOW

    def test_automated_valuation_is_low(self):
        assert (
            assess_arv(Evidence(arv_basis=ValueBasis.AUTOMATED_VALUATION)).level
            == Confidence.LOW
        )

    def test_appraisal_is_a_fact_not_an_estimate(self):
        result = assess_arv(Evidence(arv_basis=ValueBasis.APPRAISAL))
        assert result.level == Confidence.HIGH
        assert result.assertion == Assertion.FACT

    def test_list_price_is_an_inference(self):
        """An asking price is what someone wants, not what a house is worth."""
        result = assess_arv(Evidence(arv_basis=ValueBasis.LIST_PRICE))
        assert result.assertion == Assertion.INFERENCE
        assert result.level == Confidence.LOW

    def test_no_recorded_basis_is_unknown(self):
        result = assess_arv(Evidence())
        assert result.assertion == Assertion.UNKNOWN
        assert result.level == Confidence.LOW

    def test_many_comps_but_stale_downgrades_and_says_why(self):
        result = assess_arv(_comps(6, age_days=400))
        assert result.level == Confidence.MEDIUM
        assert any("older than 180 days" in r for r in result.reasons)

    def test_many_comps_but_dissimilar_downgrades(self):
        assert assess_arv(_comps(6, similarity="0.40")).level == Confidence.MEDIUM

    def test_wide_range_costs_a_confidence_level(self):
        tight = assess_arv(_comps(5), arv_low=D("245000"), arv_high=D("255000"))
        wide = assess_arv(_comps(5), arv_low=D("200000"), arv_high=D("300000"))
        assert tight.level == Confidence.HIGH
        assert wide.level == Confidence.MEDIUM
        assert any("spans more than 15%" in r for r in wide.reasons)

    def test_every_assessment_explains_itself(self):
        for evidence in (_comps(5), _comps(1), Evidence()):
            assert assess_arv(evidence).reasons


class TestRehabConfidence:
    def test_contractor_bid_is_high_and_factual(self):
        result = assess_rehab(Evidence(rehab_basis=RehabBasis.CONTRACTOR_BID))
        assert result.level == Confidence.HIGH
        assert result.assertion == Assertion.FACT

    def test_walkthrough_is_medium(self):
        assert (
            assess_rehab(Evidence(rehab_basis=RehabBasis.WALKTHROUGH)).level
            == Confidence.MEDIUM
        )

    def test_per_square_foot_rule_of_thumb_is_low(self):
        assert (
            assess_rehab(Evidence(rehab_basis=RehabBasis.PER_SQFT_ESTIMATE)).level
            == Confidence.LOW
        )

    def test_unvisited_property_is_called_out(self):
        result = assess_rehab(
            Evidence(rehab_basis=RehabBasis.PER_SQFT_ESTIMATE, property_visited=False)
        )
        assert any("walked the property" in r for r in result.reasons)

    def test_wide_rehab_range_downgrades(self):
        result = assess_rehab(
            Evidence(rehab_basis=RehabBasis.CONTRACTOR_BID),
            rehab_low=D("30000"),
            rehab_high=D("70000"),
        )
        assert result.level == Confidence.MEDIUM


class TestRentConfidence:
    def test_lease_in_place_is_a_fact(self):
        result = assess_rent(Evidence(rent_basis=RentBasis.LEASE_IN_PLACE))
        assert result.level == Confidence.HIGH
        assert result.assertion == Assertion.FACT

    def test_rental_comps_need_three_to_reach_high(self):
        assert (
            assess_rent(Evidence(rent_basis=RentBasis.RENTAL_COMPS, comp_count=3)).level
            == Confidence.HIGH
        )
        assert (
            assess_rent(Evidence(rent_basis=RentBasis.RENTAL_COMPS, comp_count=1)).level
            == Confidence.MEDIUM
        )

    def test_unknown_basis_is_low_and_unknown(self):
        result = assess_rent(Evidence())
        assert result.level == Confidence.LOW
        assert result.assertion == Assertion.UNKNOWN


class TestConfidenceCombination:
    def test_weakest_link_governs(self):
        """A chain of estimates is only as strong as its weakest input."""
        assert (
            Confidence.weakest(Confidence.HIGH, Confidence.LOW, Confidence.MEDIUM)
            == Confidence.LOW
        )

    def test_all_high_stays_high(self):
        assert Confidence.weakest(Confidence.HIGH, Confidence.HIGH) == Confidence.HIGH

    def test_empty_defaults_to_low(self):
        """Absence of evidence is never treated as evidence of quality."""
        assert Confidence.weakest() == Confidence.LOW

    def test_ordering_is_well_defined(self):
        assert Confidence.LOW.rank < Confidence.MEDIUM.rank < Confidence.HIGH.rank


class TestRangeWidth:
    def test_narrow_range_is_not_wide(self):
        assert range_is_wide(D("245000"), D("255000")) is False

    def test_wide_range_is_wide(self):
        assert range_is_wide(D("200000"), D("300000")) is True

    def test_missing_bound_is_not_wide(self):
        assert range_is_wide(None, D("300000")) is False
