"""The confidence engine.

Atlas rates *how well supported* each major estimate is, separately from the
estimate itself. This exists to prevent false precision: a $312,450 ARV derived
from an automated valuation is not the same claim as a $312,450 ARV derived
from five recent, highly similar closed sales, and the platform must never
render them identically.

Rules are deterministic and explainable — every downgrade carries a reason
string that is shown verbatim in the UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from .enums import Assertion, Confidence, RehabBasis, RentBasis, ValueBasis
from .money import D, Numeric, safe_div

# A range wider than this fraction of the midpoint costs one confidence level.
WIDE_RANGE_THRESHOLD = D("0.15")
# Comps older than this are treated as stale evidence.
STALE_COMP_DAYS = 180


@dataclass(frozen=True)
class ConfidenceAssessment:
    level: Confidence
    assertion: Assertion
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level.value,
            "assertion": self.assertion.value,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class Evidence:
    """What we actually know about where the numbers came from."""

    arv_basis: ValueBasis = ValueBasis.UNKNOWN
    comp_count: int = 0
    average_comp_similarity: Optional[Decimal] = None  # 0..1
    average_comp_age_days: Optional[int] = None
    rehab_basis: RehabBasis = RehabBasis.UNKNOWN
    rent_basis: RentBasis = RentBasis.UNKNOWN
    inspection_completed: bool = False
    title_reviewed: bool = False
    property_visited: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "arv_basis": self.arv_basis.value,
            "comp_count": self.comp_count,
            "average_comp_similarity": (
                str(self.average_comp_similarity)
                if self.average_comp_similarity is not None
                else None
            ),
            "average_comp_age_days": self.average_comp_age_days,
            "rehab_basis": self.rehab_basis.value,
            "rent_basis": self.rent_basis.value,
            "inspection_completed": self.inspection_completed,
            "title_reviewed": self.title_reviewed,
            "property_visited": self.property_visited,
        }


def _downgrade(level: Confidence) -> Confidence:
    if level == Confidence.HIGH:
        return Confidence.MEDIUM
    return Confidence.LOW


def range_is_wide(low: Optional[Numeric], high: Optional[Numeric]) -> bool:
    """True when a low/high range spans more than the tolerated fraction."""
    if low is None or high is None:
        return False
    lo, hi = D(low), D(high)
    midpoint = (lo + hi) / D(2)
    spread = safe_div(hi - lo, midpoint)
    return spread is not None and spread > WIDE_RANGE_THRESHOLD


def assess_arv(
    evidence: Evidence,
    arv_low: Optional[Numeric] = None,
    arv_high: Optional[Numeric] = None,
) -> ConfidenceAssessment:
    reasons: List[str] = []
    basis = evidence.arv_basis

    if basis == ValueBasis.APPRAISAL:
        level = Confidence.HIGH
        assertion = Assertion.FACT
        reasons.append("Value supported by a formal appraisal.")
    elif basis == ValueBasis.COMPARABLE_SALES:
        assertion = Assertion.ESTIMATE
        similarity = evidence.average_comp_similarity
        strong_similarity = similarity is not None and D(similarity) >= D("0.75")
        recent = (
            evidence.average_comp_age_days is not None
            and evidence.average_comp_age_days <= STALE_COMP_DAYS
        )
        if evidence.comp_count >= 4 and strong_similarity and recent:
            level = Confidence.HIGH
            reasons.append(
                f"{evidence.comp_count} recent closed comps with high similarity."
            )
        elif evidence.comp_count >= 2:
            level = Confidence.MEDIUM
            reasons.append(
                f"{evidence.comp_count} comps available, but similarity, recency or "
                "count falls short of a high-confidence set."
            )
        else:
            level = Confidence.LOW
            reasons.append("Fewer than two comparable sales support this value.")
        if evidence.comp_count > 0 and not recent:
            reasons.append(
                "Comparable sales are older than 180 days; market may have moved."
            )
    elif basis == ValueBasis.BROKER_OPINION:
        level = Confidence.MEDIUM
        assertion = Assertion.ESTIMATE
        reasons.append("Value based on a broker price opinion, not closed sales.")
    elif basis == ValueBasis.AUTOMATED_VALUATION:
        level = Confidence.LOW
        assertion = Assertion.ESTIMATE
        reasons.append(
            "Value based mostly on an automated estimate; AVMs miss condition."
        )
    elif basis == ValueBasis.LIST_PRICE:
        level = Confidence.LOW
        assertion = Assertion.INFERENCE
        reasons.append("Value inferred from list price, which is an asking figure.")
    elif basis == ValueBasis.USER_ENTERED:
        level = Confidence.LOW
        assertion = Assertion.ESTIMATE
        reasons.append("Value entered manually with no supporting evidence recorded.")
    else:
        return ConfidenceAssessment(
            level=Confidence.LOW,
            assertion=Assertion.UNKNOWN,
            reasons=["No basis recorded for the after-repair value."],
        )

    if range_is_wide(arv_low, arv_high):
        level = _downgrade(level)
        reasons.append("ARV range spans more than 15% of its midpoint.")

    return ConfidenceAssessment(level=level, assertion=assertion, reasons=reasons)


def assess_rehab(
    evidence: Evidence,
    rehab_low: Optional[Numeric] = None,
    rehab_high: Optional[Numeric] = None,
) -> ConfidenceAssessment:
    reasons: List[str] = []
    basis = evidence.rehab_basis

    mapping = {
        RehabBasis.CONTRACTOR_BID: (
            Confidence.HIGH,
            Assertion.FACT,
            "Rehab backed by a contractor bid.",
        ),
        RehabBasis.DETAILED_SCOPE: (
            Confidence.HIGH,
            Assertion.ESTIMATE,
            "Rehab built from a line-item scope of work.",
        ),
        RehabBasis.WALKTHROUGH: (
            Confidence.MEDIUM,
            Assertion.ESTIMATE,
            "Rehab estimated from an on-site walkthrough.",
        ),
        RehabBasis.PER_SQFT_ESTIMATE: (
            Confidence.LOW,
            Assertion.ESTIMATE,
            "Rehab estimated from a per-square-foot rule of thumb.",
        ),
        RehabBasis.USER_ENTERED: (
            Confidence.LOW,
            Assertion.ESTIMATE,
            "Rehab entered manually with no supporting scope recorded.",
        ),
    }
    if basis not in mapping:
        return ConfidenceAssessment(
            level=Confidence.LOW,
            assertion=Assertion.UNKNOWN,
            reasons=["No basis recorded for the rehab estimate."],
        )

    level, assertion, reason = mapping[basis]
    reasons.append(reason)

    if not evidence.property_visited and basis in (
        RehabBasis.PER_SQFT_ESTIMATE,
        RehabBasis.USER_ENTERED,
    ):
        reasons.append("Nobody has walked the property; hidden condition is unpriced.")
    if range_is_wide(rehab_low, rehab_high):
        level = _downgrade(level)
        reasons.append("Rehab range spans more than 15% of its midpoint.")

    return ConfidenceAssessment(level=level, assertion=assertion, reasons=reasons)


def assess_rent(evidence: Evidence) -> ConfidenceAssessment:
    basis = evidence.rent_basis
    if basis in (RentBasis.LEASE_IN_PLACE, RentBasis.RENT_ROLL):
        return ConfidenceAssessment(
            level=Confidence.HIGH,
            assertion=Assertion.FACT,
            reasons=["Rent supported by an in-place lease or rent roll."],
        )
    if basis == RentBasis.RENTAL_COMPS:
        level = Confidence.HIGH if evidence.comp_count >= 3 else Confidence.MEDIUM
        return ConfidenceAssessment(
            level=level,
            assertion=Assertion.ESTIMATE,
            reasons=["Rent estimated from rental comparables."],
        )
    if basis == RentBasis.AUTOMATED_ESTIMATE:
        return ConfidenceAssessment(
            level=Confidence.MEDIUM,
            assertion=Assertion.ESTIMATE,
            reasons=["Rent based on an automated rent estimate."],
        )
    if basis == RentBasis.USER_ENTERED:
        return ConfidenceAssessment(
            level=Confidence.LOW,
            assertion=Assertion.ESTIMATE,
            reasons=["Rent entered manually with no supporting evidence recorded."],
        )
    return ConfidenceAssessment(
        level=Confidence.LOW,
        assertion=Assertion.UNKNOWN,
        reasons=["No basis recorded for the rent estimate."],
    )
