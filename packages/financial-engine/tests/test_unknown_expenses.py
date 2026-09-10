"""Operating expenses are tri-state: a figure, an explicit zero, or unknown.

Before this, taxes, insurance and HOA defaulted to ``Decimal("0")`` and there
was no way for the engine to tell "this property has no HOA" apart from "nobody
has checked". The consequences were not cosmetic. On a typical single-family
rental the omission ran to hundreds of dollars a month, the buy box flipped
from NOT MET to MET, and the analysis still reported HIGH confidence and a
PURSUE verdict — the three signals a user relies on all agreed, and all three
were wrong.

These tests pin the behaviour that replaced it.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal as Dec

import pytest

from atlas_financial_engine import analyze_all_strategies, build_inputs
from atlas_financial_engine.assumptions import (
    ASSUMPTIONS_SCHEMA_VERSION,
    Assumptions,
    HoldingCosts,
    RentalAssumptions,
    known,
)
from atlas_financial_engine.enums import Confidence, Strategy
from atlas_financial_engine.money import D
from atlas_financial_engine.strategies.buy_hold import build_operating_statement


class TestTheThreeStates:
    def test_a_figure_is_used(self):
        rental = RentalAssumptions(annual_taxes=D("2400"))
        assert build_operating_statement(D("1800"), rental).taxes == D("2400.00")
        assert rental.unknown_fields() == ["annual_insurance", "monthly_hoa"]

    def test_an_explicit_zero_is_an_answer(self):
        rental = RentalAssumptions(
            annual_taxes=D("0"), annual_insurance=D("0"), monthly_hoa=D("0")
        )
        assert rental.unknown_fields() == []
        assert rental.blocking_unknowns() == []

    def test_unknown_is_the_default(self):
        """Nothing invented at construction time. The engine starts by knowing
        nothing about a specific property, which is the truth."""
        rental = RentalAssumptions()
        assert rental.annual_taxes is None
        assert rental.unknown_fields() == [
            "annual_taxes",
            "annual_insurance",
            "monthly_hoa",
        ]

    def test_the_defaults_carry_no_invented_utilities_figure(self):
        """The old default was $150/month, chosen by nobody in particular."""
        assert HoldingCosts().monthly_utilities is None
        assert HoldingCosts().monthly_total == D("0")


class TestArithmetic:
    def test_an_unknown_is_omitted_never_guessed(self):
        with_taxes = build_operating_statement(
            D("1800"), RentalAssumptions(annual_taxes=D("2400"))
        )
        without = build_operating_statement(D("1800"), RentalAssumptions())
        assert without.taxes == D("0.00")
        # Exactly the missing figure, not an estimate of it.
        assert without.net_operating_income - with_taxes.net_operating_income == D("2400")

    def test_omission_is_the_optimistic_direction_and_that_is_the_point(self):
        """Atlas errs high and says so, rather than erring plausibly in silence.

        A guessed expense would be indistinguishable from a known one in the
        output; an omitted one is reported by every channel below.
        """
        unknown = build_inputs(
            purchase_price=150_000, arv=250_000, rehab=45_000, monthly_rent=1_800
        )
        comparison = analyze_all_strategies(unknown)
        assert "rental.annual_taxes" in comparison.missing_information
        assert comparison.overall_confidence != Confidence.HIGH

    def test_known_returns_zero_only_for_none(self):
        assert known(None) == D("0")
        assert known(D("0")) == D("0")
        assert known(D("2400")) == D("2400")


class TestReporting:
    @pytest.fixture
    def complete(self) -> Assumptions:
        return Assumptions(
            holding=HoldingCosts(
                annual_taxes=D("2400"),
                annual_insurance=D("1800"),
                monthly_hoa=D("0"),
                monthly_utilities=D("150"),
            ),
            rental=RentalAssumptions(
                annual_taxes=D("2400"), annual_insurance=D("1800"), monthly_hoa=D("0")
            ),
        )

    def test_blocking_unknowns_are_taxes_and_insurance_only(self):
        """HOA and utilities are reported but do not block.

        Most properties have no HOA and many rentals are tenant-metered, so an
        unknown there is frequently a real zero. Blocking on it would fire on
        nearly every deal, and a flag that always fires is a flag nobody reads.
        """
        a = Assumptions()
        assert a.blocking_unknown_expenses() == [
            "holding.annual_taxes",
            "holding.annual_insurance",
            "rental.annual_taxes",
            "rental.annual_insurance",
        ]
        assert "monthly_hoa" in a.unknown_expenses()["holding"]

    def test_a_complete_set_blocks_nothing(self, complete: Assumptions):
        assert complete.blocking_unknown_expenses() == []
        assert complete.unknown_expenses() == {"holding": [], "rental": []}

    def test_confidence_is_capped_at_medium(self, complete: Assumptions):
        """Even with strong comps and a contractor bid, a cash flow missing an
        expense every property incurs is not a HIGH-confidence figure."""
        base = build_inputs(
            purchase_price=150_000,
            arv=250_000,
            rehab=45_000,
            monthly_rent=1_800,
            assumptions=complete.to_dict(),
            evidence={
                "arv_basis": "appraisal",
                "rent_basis": "lease_in_place",
                "rehab_basis": "contractor_bid",
                "comp_count": 5,
                "average_comp_similarity": "0.9",
                "average_comp_age_days": 30,
            },
        )
        assert analyze_all_strategies(base).overall_confidence == Confidence.HIGH

        without_taxes = replace(
            base,
            assumptions=replace(
                complete, rental=replace(complete.rental, annual_taxes=None)
            ),
        )
        comparison = analyze_all_strategies(without_taxes)
        assert comparison.overall_confidence == Confidence.MEDIUM
        assert any(
            "capped at MEDIUM" in reason
            for result in comparison.results.values()
            for reason in result.confidence_reasons
        )

    def test_the_cap_names_what_is_missing(self, complete: Assumptions):
        inputs = build_inputs(
            purchase_price=150_000,
            arv=250_000,
            rehab=45_000,
            monthly_rent=1_800,
            assumptions=replace(
                complete, rental=replace(complete.rental, annual_insurance=None)
            ).to_dict(),
        )
        buy_hold = analyze_all_strategies(inputs).results[Strategy.BUY_HOLD]
        assert "rental.annual_insurance" in buy_hold.missing_inputs


class TestSchemaVersioning:
    """A stored analysis must keep meaning what it meant when it was saved."""

    def test_a_legacy_zero_is_read_back_as_unknown(self):
        legacy = {
            "rental": {"annual_taxes": "0", "annual_insurance": "0"},
            "holding": {"annual_taxes": "0", "annual_insurance": "0"},
        }
        a = Assumptions.from_dict(legacy)
        assert a.rental.annual_taxes is None
        assert a.holding.annual_insurance is None
        assert a.schema_version == ASSUMPTIONS_SCHEMA_VERSION

    def test_a_legacy_figure_is_left_alone(self):
        """Only the zero was ambiguous. A real number someone typed stays."""
        a = Assumptions.from_dict({"rental": {"annual_taxes": "3200"}})
        assert a.rental.annual_taxes == D("3200")

    def test_a_legacy_analysis_still_reproduces_its_utilities(self):
        """$150/month was invented, but it is what the stored figures were
        computed with. Dropping it would change a saved analysis's arithmetic
        after the fact, which is worse than carrying an old guess forward."""
        a = Assumptions.from_dict({"rental": {"annual_taxes": "2400"}})
        assert a.holding.monthly_utilities == D("150")

    def test_a_current_blob_is_not_migrated(self):
        """An explicit zero written under the current schema is an answer, and
        a round trip must not quietly turn it back into an unknown."""
        current = Assumptions(
            rental=RentalAssumptions(annual_taxes=D("0")),
            holding=HoldingCosts(monthly_utilities=D("0")),
        )
        restored = Assumptions.from_dict(current.to_dict())
        assert restored.rental.annual_taxes == D("0")
        assert restored.holding.monthly_utilities == D("0")

    def test_an_emptied_form_field_is_unknown_not_zero(self):
        """The browser sends "" for a cleared input."""
        a = Assumptions.from_dict(
            {"schema_version": ASSUMPTIONS_SCHEMA_VERSION, "rental": {"annual_taxes": ""}}
        )
        assert a.rental.annual_taxes is None

    def test_a_round_trip_is_stable(self):
        a = Assumptions(
            rental=RentalAssumptions(annual_taxes=D("2400"), monthly_hoa=D("0"))
        )
        assert Assumptions.from_dict(a.to_dict()).to_dict() == a.to_dict()

    def test_unknown_survives_serialization_as_null(self):
        assert Assumptions().to_dict()["rental"]["annual_taxes"] is None


class TestDecimalDiscipline:
    def test_no_floats_leak_in(self):
        statement = build_operating_statement(
            D("1800"), RentalAssumptions(annual_taxes=D("2400"))
        )
        assert all(
            isinstance(v, Dec) for v in vars(statement).values()
        )
