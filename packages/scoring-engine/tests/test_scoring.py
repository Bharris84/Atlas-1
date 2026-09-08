"""Deal scoring and risk flag behaviour.

The behaviour that matters most: a hard risk flag must beat a good score.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from atlas_financial_engine import (
    Assumptions,
    Confidence,
    DealInputs,
    Evidence,
    HoldingCosts,
    PropertyFacts,
    RehabBasis,
    RentBasis,
    RentalAssumptions,
    RiskSeverity,
    ValueBasis,
    Verdict,
    analyze_all_strategies,
)
from atlas_financial_engine.money import D
from atlas_scoring_engine import (
    ScoringWeights,
    all_risk_flags,
    compute_risk_score,
    score_deal,
)


@pytest.fixture
def assumptions() -> Assumptions:
    return Assumptions(
        holding=HoldingCosts(annual_taxes=D("2400"), annual_insurance=D("1800")),
        rental=RentalAssumptions(annual_taxes=D("2400"), annual_insurance=D("1800")),
    )


@pytest.fixture
def strong_deal(assumptions: Assumptions) -> DealInputs:
    """A well-evidenced deal priced to work."""
    return DealInputs(
        purchase_price=D("95000"),
        arv=D("250000"),
        rehab=D("45000"),
        monthly_rent=D("1800"),
        assumptions=assumptions,
        property_facts=PropertyFacts(
            property_type="single_family",
            bedrooms=D("3"),
            bathrooms=D("2"),
            square_feet=D("1450"),
            year_built=1998,
            state="TN",
        ),
        evidence=Evidence(
            arv_basis=ValueBasis.COMPARABLE_SALES,
            comp_count=5,
            average_comp_similarity=D("0.85"),
            average_comp_age_days=90,
            rehab_basis=RehabBasis.CONTRACTOR_BID,
            rent_basis=RentBasis.RENTAL_COMPS,
            property_visited=True,
            inspection_completed=True,
            title_reviewed=True,
        ),
    )


def _score(inputs: DealInputs):
    return score_deal(inputs, analyze_all_strategies(inputs))


class TestScoring:
    def test_a_strong_well_evidenced_deal_scores_well(self, strong_deal: DealInputs):
        result = _score(strong_deal)
        assert result.score > D("60")
        assert result.verdict in (Verdict.PURSUE, Verdict.INVESTIGATE)

    def test_score_is_bounded(self, strong_deal: DealInputs):
        assert D("0") <= _score(strong_deal).score <= D("100")

    def test_overpriced_deal_scores_worse_than_a_good_one(self, strong_deal: DealInputs):
        bad = replace(strong_deal, purchase_price=D("235000"))
        assert _score(bad).score < _score(strong_deal).score

    def test_components_are_reported_with_weights_and_reasons(
        self, strong_deal: DealInputs
    ):
        for component in _score(strong_deal).components:
            assert component.reason
            assert component.weight > 0

    def test_weights_sum_to_one(self):
        assert sum(ScoringWeights().as_dict().values()) == D("1.00")


class TestUnassessableCategories:
    def test_seller_and_market_are_declared_unassessed_not_guessed(
        self, strong_deal: DealInputs
    ):
        """Atlas never pads a score with an invented average."""
        components = {c.name: c for c in _score(strong_deal).components}
        assert components["seller_situation"].assessed is False
        assert components["seller_situation"].score is None
        assert components["market"].assessed is False

    def test_seller_component_explicitly_refuses_to_infer_motivation(
        self, strong_deal: DealInputs
    ):
        components = {c.name: c for c in _score(strong_deal).components}
        assert "does not infer motivation" in components["seller_situation"].reason

    def test_coverage_reports_the_share_of_the_rubric_actually_scored(
        self, strong_deal: DealInputs
    ):
        result = _score(strong_deal)
        expected = sum(c.weight for c in result.components if c.assessed)
        assert result.coverage == expected
        assert result.coverage < D("1")

    def test_score_is_renormalised_over_assessed_categories_only(
        self, strong_deal: DealInputs
    ):
        result = _score(strong_deal)
        assessed = [c for c in result.components if c.assessed]
        expected = sum(c.score * c.weight for c in assessed) / sum(
            c.weight for c in assessed
        )
        assert abs(result.score - expected) < D("0.01")

    def test_thin_coverage_cannot_reach_pursue(self, assumptions: Assumptions):
        """A great score on a third of the rubric is not a decision."""
        sparse = DealInputs(
            purchase_price=D("60000"),
            arv=D("250000"),
            rehab=D("30000"),
            monthly_rent=D("2200"),
            assumptions=assumptions,
            evidence=Evidence(
                arv_basis=ValueBasis.APPRAISAL,
                rehab_basis=RehabBasis.CONTRACTOR_BID,
                rent_basis=RentBasis.LEASE_IN_PLACE,
                property_visited=True,
                inspection_completed=True,
                title_reviewed=True,
            ),
        )
        result = _score(sparse)
        # Excellent economics and perfect evidence, but no property details at
        # all, so the rubric is only 60% covered.
        assert result.score >= D("80")
        assert result.coverage == D("0.6000")
        assert result.verdict == Verdict.INVESTIGATE
        assert "rubric could be assessed" in result.verdict_reason

    def test_recording_property_details_unlocks_pursue(self, strong_deal: DealInputs):
        """The same deal, with the house actually described, can be pursued."""
        cheap = replace(strong_deal, purchase_price=D("60000"))
        result = _score(cheap)
        assert result.coverage == D("0.7000")
        assert result.verdict == Verdict.PURSUE


class TestRiskOverrides:
    def test_a_blocking_flag_beats_a_good_score(self, strong_deal: DealInputs):
        flagged = replace(strong_deal, risk_flags=["structural_concern"])
        result = _score(flagged)
        assert result.verdict == Verdict.HUMAN_REVIEW_REQUIRED
        assert result.requires_human_review is True
        assert "Structural uncertainty" in result.verdict_reason

    def test_score_is_still_reported_alongside_the_override(self, strong_deal: DealInputs):
        """The override changes the decision, it does not hide the arithmetic."""
        flagged = replace(strong_deal, risk_flags=["environmental_concern"])
        result = _score(flagged)
        assert result.score is not None
        assert result.verdict == Verdict.HUMAN_REVIEW_REQUIRED

    @pytest.mark.parametrize(
        "code",
        [
            "title_issue_suspected",
            "structural_concern",
            "environmental_concern",
            "financing_uncertainty",
        ],
    )
    def test_each_hard_risk_forces_human_review(self, strong_deal: DealInputs, code: str):
        assert _score(replace(strong_deal, risk_flags=[code])).verdict == (
            Verdict.HUMAN_REVIEW_REQUIRED
        )

    def test_unverified_arv_blocks_automatically(self, strong_deal: DealInputs):
        """An ARV nobody verified is the single most dangerous input in Atlas."""
        guessed = replace(
            strong_deal,
            evidence=replace(strong_deal.evidence, arv_basis=ValueBasis.AUTOMATED_VALUATION),
        )
        result = _score(guessed)
        codes = {f.code for f in result.risk_flags}
        assert "unverified_arv" in codes
        assert result.verdict == Verdict.HUMAN_REVIEW_REQUIRED

    def test_heavy_rehab_on_a_guess_blocks(self, strong_deal: DealInputs):
        reckless = replace(
            strong_deal,
            rehab=D("100000"),
            evidence=replace(strong_deal.evidence, rehab_basis=RehabBasis.USER_ENTERED),
        )
        codes = {f.code for f in _score(reckless).risk_flags}
        assert "unrealistic_rehab_assumptions" in codes

    def test_a_warning_does_not_block(self, strong_deal: DealInputs):
        warned = replace(strong_deal, risk_flags=["hoa_restrictions"])
        result = _score(warned)
        assert result.requires_human_review is False
        assert any(f.code == "hoa_restrictions" for f in result.risk_flags)

    def test_unknown_declared_flag_is_kept_not_dropped(self, strong_deal: DealInputs):
        """A risk someone recorded must never silently disappear."""
        odd = replace(strong_deal, risk_flags=["neighbour_dispute"])
        flags = {f.code: f for f in _score(odd).risk_flags}
        assert "neighbour_dispute" in flags
        assert flags["neighbour_dispute"].severity == RiskSeverity.WARNING

    def test_no_viable_strategy_requires_review(self, assumptions: Assumptions):
        result = _score(DealInputs(assumptions=assumptions))
        assert result.verdict == Verdict.HUMAN_REVIEW_REQUIRED


class TestDerivedFlags:
    def test_unvisited_property_is_flagged(self, strong_deal: DealInputs):
        unvisited = replace(
            strong_deal, evidence=replace(strong_deal.evidence, property_visited=False)
        )
        assert "property_not_inspected" in {f.code for f in _score(unvisited).risk_flags}

    def test_untitled_deal_is_flagged_but_not_blocked(self, strong_deal: DealInputs):
        no_title = replace(
            strong_deal, evidence=replace(strong_deal.evidence, title_reviewed=False)
        )
        result = _score(no_title)
        assert "title_not_reviewed" in {f.code for f in result.risk_flags}
        assert result.requires_human_review is False

    def test_old_construction_without_inspection_is_flagged(self, strong_deal: DealInputs):
        old = replace(
            strong_deal,
            property_facts=replace(strong_deal.property_facts, year_built=1925),
            evidence=replace(strong_deal.evidence, inspection_completed=False),
        )
        assert "older_construction_uninspected" in {f.code for f in _score(old).risk_flags}

    def test_single_exit_is_flagged_as_fragile(self, strong_deal: DealInputs):
        comparison = analyze_all_strategies(strong_deal)
        flags = {f.code for f in all_risk_flags(strong_deal, comparison)}
        if comparison.viable_exit_count == 1:
            assert "single_exit" in flags

    def test_flags_are_ordered_most_severe_first(self, strong_deal: DealInputs):
        flagged = replace(strong_deal, risk_flags=["structural_concern", "hoa_restrictions"])
        severities = [f.severity for f in _score(flagged).risk_flags]
        assert severities[0] == RiskSeverity.CRITICAL

    def test_flags_are_deduplicated(self, strong_deal: DealInputs):
        dupes = replace(strong_deal, risk_flags=["hoa_restrictions", "hoa_restrictions"])
        codes = [f.code for f in _score(dupes).risk_flags]
        assert len(codes) == len(set(codes))

    def test_every_flag_explains_itself(self, strong_deal: DealInputs):
        flagged = replace(strong_deal, risk_flags=["flood_zone"])
        for flag in _score(flagged).risk_flags:
            assert flag.detail
            assert flag.label


class TestRiskScore:
    def test_high_confidence_and_no_flags_scores_high(self):
        assert compute_risk_score([], Confidence.HIGH) == D("90.0000")

    def test_low_confidence_scores_lower(self):
        assert compute_risk_score([], Confidence.LOW) < compute_risk_score(
            [], Confidence.HIGH
        )

    def test_risk_score_is_floored_at_zero(self, strong_deal: DealInputs):
        piled_on = replace(
            strong_deal,
            risk_flags=[
                "structural_concern",
                "environmental_concern",
                "title_issue_suspected",
                "financing_uncertainty",
            ],
        )
        assert _score(piled_on).risk_score >= 0


class TestSerialization:
    def test_score_serialises_to_json(self, strong_deal: DealInputs):
        import json

        payload = _score(strong_deal).to_dict()
        assert json.loads(json.dumps(payload))["verdict"]

    def test_scoring_is_deterministic(self, strong_deal: DealInputs):
        import json

        first = json.dumps(_score(strong_deal).to_dict(), sort_keys=True)
        second = json.dumps(_score(strong_deal).to_dict(), sort_keys=True)
        assert first == second
