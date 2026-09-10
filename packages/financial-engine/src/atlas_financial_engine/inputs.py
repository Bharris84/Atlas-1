"""Inputs to the financial engine.

The engine is deliberately decoupled from the database and the API: it takes a
plain ``DealInputs`` value object and returns plain result objects. Nothing in
here imports SQLAlchemy, FastAPI or an AI client.

Missing values are represented as ``None``, never as ``0``. A property with no
rent estimate is not a property that rents for nothing, and the strategy engine
must be able to tell those two situations apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Mapping, Optional

from .assumptions import Assumptions
from .confidence import Evidence
from .enums import RehabBasis, RentBasis, ValueBasis
from .investor import InvestorProfile
from .money import D, Numeric


def _opt(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    return D(value)


def _midpoint(
    point: Optional[Decimal], low: Optional[Decimal], high: Optional[Decimal]
) -> Optional[Decimal]:
    """Prefer an explicit point estimate; otherwise take the range midpoint."""
    if point is not None:
        return point
    if low is not None and high is not None:
        return (low + high) / D(2)
    return low if low is not None else high


@dataclass(frozen=True)
class PropertyFacts:
    """Descriptive facts. Not used for arithmetic, used for risk and context."""

    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    county: Optional[str] = None
    property_type: Optional[str] = None
    bedrooms: Optional[Decimal] = None
    bathrooms: Optional[Decimal] = None
    square_feet: Optional[Decimal] = None
    lot_size: Optional[Decimal] = None
    year_built: Optional[int] = None
    occupancy: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "address": self.address,
            "city": self.city,
            "state": self.state,
            "zip_code": self.zip_code,
            "county": self.county,
            "property_type": self.property_type,
            "bedrooms": str(self.bedrooms) if self.bedrooms is not None else None,
            "bathrooms": str(self.bathrooms) if self.bathrooms is not None else None,
            "square_feet": str(self.square_feet) if self.square_feet is not None else None,
            "lot_size": str(self.lot_size) if self.lot_size is not None else None,
            "year_built": self.year_built,
            "occupancy": self.occupancy,
        }


@dataclass(frozen=True)
class DealInputs:
    """Everything the engine needs to underwrite one property."""

    purchase_price: Optional[Decimal] = None
    arv: Optional[Decimal] = None
    arv_low: Optional[Decimal] = None
    arv_high: Optional[Decimal] = None
    rehab: Optional[Decimal] = None
    rehab_low: Optional[Decimal] = None
    rehab_high: Optional[Decimal] = None
    monthly_rent: Optional[Decimal] = None
    as_is_value: Optional[Decimal] = None
    listing_price: Optional[Decimal] = None

    property_facts: PropertyFacts = field(default_factory=PropertyFacts)
    assumptions: Assumptions = field(default_factory=Assumptions)
    evidence: Evidence = field(default_factory=Evidence)
    # Describes the INVESTOR, not the deal. Optional: an unstated profile means
    # capital-constraint questions are reported as unknown, never assumed.
    investor_profile: InvestorProfile = field(default_factory=InvestorProfile)

    # Free-form flags a user or the research agent can raise. These feed the
    # risk engine; see scoring-engine for how they gate a PURSUE verdict.
    risk_flags: List[str] = field(default_factory=list)

    @property
    def effective_arv(self) -> Optional[Decimal]:
        return _midpoint(self.arv, self.arv_low, self.arv_high)

    @property
    def effective_rehab(self) -> Optional[Decimal]:
        return _midpoint(self.rehab, self.rehab_low, self.rehab_high)

    def missing_fields(self) -> List[str]:
        """Inputs whose absence limits what the engine can conclude."""
        missing: List[str] = []
        if self.purchase_price is None:
            missing.append("purchase_price")
        if self.effective_arv is None:
            missing.append("arv")
        if self.effective_rehab is None:
            missing.append("rehab")
        if self.monthly_rent is None:
            missing.append("monthly_rent")
        # Operating expenses are tri-state: an explicit 0 is an answer ("this
        # property has no HOA"), so only None counts as missing. Reported with
        # their section because holding-period taxes and rental-period taxes
        # are separately editable and can legitimately differ.
        for section, unknown in self.assumptions.unknown_expenses().items():
            missing.extend(f"{section}.{name}" for name in unknown)
        return missing

    def to_dict(self) -> Dict[str, Any]:
        def s(v: Optional[Decimal]) -> Optional[str]:
            return str(v) if v is not None else None

        return {
            "purchase_price": s(self.purchase_price),
            "arv": s(self.arv),
            "arv_low": s(self.arv_low),
            "arv_high": s(self.arv_high),
            "rehab": s(self.rehab),
            "rehab_low": s(self.rehab_low),
            "rehab_high": s(self.rehab_high),
            "monthly_rent": s(self.monthly_rent),
            "as_is_value": s(self.as_is_value),
            "listing_price": s(self.listing_price),
            "property_facts": self.property_facts.to_dict(),
            "assumptions": self.assumptions.to_dict(),
            "evidence": self.evidence.to_dict(),
            "investor_profile": self.investor_profile.to_dict(),
            "risk_flags": list(self.risk_flags),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DealInputs":
        facts_raw = data.get("property_facts") or {}
        evidence_raw = data.get("evidence") or {}
        return cls(
            purchase_price=_opt(data.get("purchase_price")),
            arv=_opt(data.get("arv")),
            arv_low=_opt(data.get("arv_low")),
            arv_high=_opt(data.get("arv_high")),
            rehab=_opt(data.get("rehab")),
            rehab_low=_opt(data.get("rehab_low")),
            rehab_high=_opt(data.get("rehab_high")),
            monthly_rent=_opt(data.get("monthly_rent")),
            as_is_value=_opt(data.get("as_is_value")),
            listing_price=_opt(data.get("listing_price")),
            property_facts=PropertyFacts(
                address=facts_raw.get("address"),
                city=facts_raw.get("city"),
                state=facts_raw.get("state"),
                zip_code=facts_raw.get("zip_code"),
                county=facts_raw.get("county"),
                property_type=facts_raw.get("property_type"),
                bedrooms=_opt(facts_raw.get("bedrooms")),
                bathrooms=_opt(facts_raw.get("bathrooms")),
                square_feet=_opt(facts_raw.get("square_feet")),
                lot_size=_opt(facts_raw.get("lot_size")),
                year_built=(
                    int(facts_raw["year_built"])
                    if facts_raw.get("year_built") is not None
                    else None
                ),
                occupancy=facts_raw.get("occupancy"),
            ),
            assumptions=Assumptions.from_dict(data.get("assumptions")),
            investor_profile=InvestorProfile.from_dict(data.get("investor_profile")),
            evidence=Evidence(
                arv_basis=ValueBasis(evidence_raw.get("arv_basis", ValueBasis.UNKNOWN.value)),
                comp_count=int(evidence_raw.get("comp_count") or 0),
                average_comp_similarity=_opt(evidence_raw.get("average_comp_similarity")),
                average_comp_age_days=(
                    int(evidence_raw["average_comp_age_days"])
                    if evidence_raw.get("average_comp_age_days") is not None
                    else None
                ),
                rehab_basis=RehabBasis(
                    evidence_raw.get("rehab_basis", RehabBasis.UNKNOWN.value)
                ),
                rent_basis=RentBasis(evidence_raw.get("rent_basis", RentBasis.UNKNOWN.value)),
                inspection_completed=bool(evidence_raw.get("inspection_completed", False)),
                title_reviewed=bool(evidence_raw.get("title_reviewed", False)),
                property_visited=bool(evidence_raw.get("property_visited", False)),
            ),
            risk_flags=list(data.get("risk_flags") or []),
        )


def build_inputs(
    *,
    purchase_price: Optional[Numeric] = None,
    arv: Optional[Numeric] = None,
    rehab: Optional[Numeric] = None,
    monthly_rent: Optional[Numeric] = None,
    **kwargs: Any,
) -> DealInputs:
    """Convenience constructor that coerces loose numeric input."""
    payload: Dict[str, Any] = {
        "purchase_price": purchase_price,
        "arv": arv,
        "rehab": rehab,
        "monthly_rent": monthly_rent,
    }
    payload.update(kwargs)
    return DealInputs.from_dict(payload)
