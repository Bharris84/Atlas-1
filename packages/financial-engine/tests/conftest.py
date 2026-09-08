"""Shared fixtures.

The baseline deal is a deliberately ordinary southeastern single-family house:
$150k purchase, $250k ARV, $45k rehab, $1,800 rent. Most tests perturb one
variable off this baseline so a failure points at the variable, not the setup.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from atlas_financial_engine import (
    Assumptions,
    DealInputs,
    Evidence,
    HoldingCosts,
    RehabBasis,
    RentBasis,
    RentalAssumptions,
    ValueBasis,
)
from atlas_financial_engine.money import D


@pytest.fixture
def strong_evidence() -> Evidence:
    return Evidence(
        arv_basis=ValueBasis.COMPARABLE_SALES,
        comp_count=5,
        average_comp_similarity=D("0.85"),
        average_comp_age_days=90,
        rehab_basis=RehabBasis.CONTRACTOR_BID,
        rent_basis=RentBasis.RENTAL_COMPS,
        property_visited=True,
        inspection_completed=True,
        title_reviewed=True,
    )


@pytest.fixture
def assumptions() -> Assumptions:
    """Baseline assumptions with real (non-zero) taxes and insurance."""
    return Assumptions(
        holding=HoldingCosts(
            annual_taxes=D("2400"),
            annual_insurance=D("1800"),
            monthly_utilities=D("150"),
        ),
        rental=RentalAssumptions(
            annual_taxes=D("2400"),
            annual_insurance=D("1800"),
        ),
    )


@pytest.fixture
def baseline(assumptions: Assumptions, strong_evidence: Evidence) -> DealInputs:
    return DealInputs(
        purchase_price=D("150000"),
        arv=D("250000"),
        rehab=D("45000"),
        monthly_rent=D("1800"),
        assumptions=assumptions,
        evidence=strong_evidence,
    )


@pytest.fixture
def cents() -> Decimal:
    """Tolerance for comparisons that cross a rounding boundary."""
    return D("0.02")
