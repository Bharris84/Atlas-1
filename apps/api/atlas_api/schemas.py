"""Request and response schemas.

Every inbound payload is validated here before it reaches a model or the
financial engine. Money fields are constrained where a negative value would be
nonsensical, and free-text fields are length-bounded.

Decimals serialise to JSON strings (Pydantic's default), which matches the
financial engine's output and keeps precision intact across the wire.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# --- Vocabulary -------------------------------------------------------------

LEAD_TYPES = {
    "FSBO",
    "expired",
    "vacant",
    "absentee",
    "high_equity",
    "tax_delinquent",
    "probate",
    "code_violation",
    "pre_foreclosure",
    "tired_landlord",
    "price_reduction",
    "long_DOM",
    "off_market",
    "other",
}

PROPERTY_STATUSES = {
    "prospect",
    "analyzing",
    "offer_made",
    "under_contract",
    "closed",
    "rehabbing",
    "listed",
    "rented",
    "sold",
    "dead",
}

LEAD_STATUSES = {"new", "contacted", "negotiating", "under_contract", "won", "lost", "dead"}


class AtlasModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


# --- Properties -------------------------------------------------------------


class PropertyBase(AtlasModel):
    address: str = Field(min_length=3, max_length=300)
    city: Optional[str] = Field(default=None, max_length=120)
    state: Optional[str] = Field(default=None, min_length=2, max_length=2)
    zip_code: Optional[str] = Field(default=None, max_length=12)
    county: Optional[str] = Field(default=None, max_length=120)
    parcel_apn: Optional[str] = Field(default=None, max_length=80)
    property_type: Optional[str] = Field(default=None, max_length=50)
    bedrooms: Optional[Decimal] = Field(default=None, ge=0, le=100)
    bathrooms: Optional[Decimal] = Field(default=None, ge=0, le=100)
    square_feet: Optional[Decimal] = Field(default=None, ge=0, le=1_000_000)
    lot_size: Optional[Decimal] = Field(default=None, ge=0)
    year_built: Optional[int] = Field(default=None, ge=1600, le=2100)
    property_status: str = Field(default="prospect", max_length=40)
    listing_price: Optional[Decimal] = Field(default=None, ge=0)
    estimated_value: Optional[Decimal] = Field(default=None, ge=0)
    estimated_rent: Optional[Decimal] = Field(default=None, ge=0)
    days_on_market: Optional[int] = Field(default=None, ge=0)
    latitude: Optional[Decimal] = Field(default=None, ge=-90, le=90)
    longitude: Optional[Decimal] = Field(default=None, ge=-180, le=180)
    notes: Optional[str] = Field(default=None, max_length=20_000)

    @field_validator("state")
    @classmethod
    def _uppercase_state(cls, v: Optional[str]) -> Optional[str]:
        return v.upper() if v else v

    @field_validator("property_status")
    @classmethod
    def _known_status(cls, v: str) -> str:
        if v not in PROPERTY_STATUSES:
            raise ValueError(f"property_status must be one of: {sorted(PROPERTY_STATUSES)}")
        return v


class PropertyCreate(PropertyBase):
    pass


class PropertyUpdate(AtlasModel):
    """All fields optional; only what is supplied is changed."""

    address: Optional[str] = Field(default=None, min_length=3, max_length=300)
    city: Optional[str] = Field(default=None, max_length=120)
    state: Optional[str] = Field(default=None, min_length=2, max_length=2)
    zip_code: Optional[str] = Field(default=None, max_length=12)
    county: Optional[str] = Field(default=None, max_length=120)
    parcel_apn: Optional[str] = Field(default=None, max_length=80)
    property_type: Optional[str] = Field(default=None, max_length=50)
    bedrooms: Optional[Decimal] = Field(default=None, ge=0, le=100)
    bathrooms: Optional[Decimal] = Field(default=None, ge=0, le=100)
    square_feet: Optional[Decimal] = Field(default=None, ge=0, le=1_000_000)
    lot_size: Optional[Decimal] = Field(default=None, ge=0)
    year_built: Optional[int] = Field(default=None, ge=1600, le=2100)
    property_status: Optional[str] = Field(default=None, max_length=40)
    listing_price: Optional[Decimal] = Field(default=None, ge=0)
    estimated_value: Optional[Decimal] = Field(default=None, ge=0)
    estimated_rent: Optional[Decimal] = Field(default=None, ge=0)
    days_on_market: Optional[int] = Field(default=None, ge=0)
    latitude: Optional[Decimal] = Field(default=None, ge=-90, le=90)
    longitude: Optional[Decimal] = Field(default=None, ge=-180, le=180)
    notes: Optional[str] = Field(default=None, max_length=20_000)

    @field_validator("state")
    @classmethod
    def _uppercase_state(cls, v: Optional[str]) -> Optional[str]:
        return v.upper() if v else v

    @field_validator("property_status")
    @classmethod
    def _known_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in PROPERTY_STATUSES:
            raise ValueError(f"property_status must be one of: {sorted(PROPERTY_STATUSES)}")
        return v


class PropertyRead(PropertyBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class PropertySummary(AtlasModel):
    """Property plus its latest analysis headline, for list views."""

    id: uuid.UUID
    address: str
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    property_type: Optional[str] = None
    property_status: str
    bedrooms: Optional[Decimal] = None
    bathrooms: Optional[Decimal] = None
    square_feet: Optional[Decimal] = None
    estimated_value: Optional[Decimal] = None
    updated_at: datetime
    latest_analysis_id: Optional[uuid.UUID] = None
    deal_score: Optional[Decimal] = None
    verdict: Optional[str] = None
    recommended_strategy: Optional[str] = None
    profit: Optional[Decimal] = None
    cash_required: Optional[Decimal] = None
    confidence: Optional[str] = None
    requires_human_review: bool = False


# --- Owners -----------------------------------------------------------------


class OwnerBase(AtlasModel):
    owner_name: Optional[str] = Field(default=None, max_length=300)
    entity_type: Optional[str] = Field(default=None, max_length=60)
    mailing_address: Optional[str] = Field(default=None, max_length=300)
    ownership_start_date: Optional[date] = None
    estimated_equity: Optional[Decimal] = None
    estimated_mortgage: Optional[Decimal] = Field(default=None, ge=0)
    occupancy_indicator: Optional[str] = Field(default=None, max_length=40)
    notes: Optional[str] = Field(default=None, max_length=20_000)


class OwnerCreate(OwnerBase):
    pass


class OwnerRead(OwnerBase):
    id: uuid.UUID
    property_id: uuid.UUID
    created_at: datetime


# --- Leads ------------------------------------------------------------------


class LeadBase(AtlasModel):
    lead_type: str = Field(max_length=40)
    source: Optional[str] = Field(default=None, max_length=120)
    status: str = Field(default="new", max_length=40)
    lead_score: Optional[Decimal] = Field(default=None, ge=0, le=100)
    notes: Optional[str] = Field(default=None, max_length=20_000)

    @field_validator("lead_type")
    @classmethod
    def _known_lead_type(cls, v: str) -> str:
        if v not in LEAD_TYPES:
            raise ValueError(f"lead_type must be one of: {sorted(LEAD_TYPES)}")
        return v

    @field_validator("status")
    @classmethod
    def _known_status(cls, v: str) -> str:
        if v not in LEAD_STATUSES:
            raise ValueError(f"status must be one of: {sorted(LEAD_STATUSES)}")
        return v


class LeadCreate(LeadBase):
    property_id: uuid.UUID


class LeadUpdate(AtlasModel):
    status: Optional[str] = Field(default=None, max_length=40)
    lead_score: Optional[Decimal] = Field(default=None, ge=0, le=100)
    source: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = Field(default=None, max_length=20_000)

    @field_validator("status")
    @classmethod
    def _known_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in LEAD_STATUSES:
            raise ValueError(f"status must be one of: {sorted(LEAD_STATUSES)}")
        return v


class LeadRead(LeadBase):
    id: uuid.UUID
    property_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# --- Comps ------------------------------------------------------------------


class CompBase(AtlasModel):
    address: str = Field(min_length=3, max_length=300)
    distance_miles: Optional[Decimal] = Field(default=None, ge=0)
    sale_price: Optional[Decimal] = Field(default=None, ge=0)
    sale_date: Optional[date] = None
    bedrooms: Optional[Decimal] = Field(default=None, ge=0, le=100)
    bathrooms: Optional[Decimal] = Field(default=None, ge=0, le=100)
    square_feet: Optional[Decimal] = Field(default=None, ge=0)
    lot_size: Optional[Decimal] = Field(default=None, ge=0)
    year_built: Optional[int] = Field(default=None, ge=1600, le=2100)
    property_type: Optional[str] = Field(default=None, max_length=50)
    condition: Optional[str] = Field(default=None, max_length=50)
    price_per_square_foot: Optional[Decimal] = Field(default=None, ge=0)
    similarity_score: Optional[Decimal] = Field(default=None, ge=0, le=1)
    source: Optional[str] = Field(default=None, max_length=80)


class CompCreate(CompBase):
    pass


class CompRead(CompBase):
    id: uuid.UUID
    property_id: uuid.UUID
    created_at: datetime


# --- Offers -----------------------------------------------------------------


class OfferBase(AtlasModel):
    offer_amount: Decimal = Field(ge=0)
    offer_type: Optional[str] = Field(default=None, max_length=50)
    terms: Optional[str] = Field(default=None, max_length=20_000)
    status: str = Field(default="draft", max_length=40)
    date_submitted: Optional[date] = None
    expiration_date: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=20_000)


class OfferCreate(OfferBase):
    pass


class OfferRead(OfferBase):
    id: uuid.UUID
    property_id: uuid.UUID
    created_at: datetime


# --- Communications ---------------------------------------------------------


class CommunicationBase(AtlasModel):
    contact_name: Optional[str] = Field(default=None, max_length=200)
    contact_role: Optional[str] = Field(default=None, max_length=80)
    communication_type: str = Field(max_length=40)
    direction: str = Field(default="outbound", max_length=20)
    occurred_at: Optional[datetime] = None
    notes: Optional[str] = Field(default=None, max_length=20_000)
    outcome: Optional[str] = Field(default=None, max_length=120)
    follow_up_at: Optional[datetime] = None


class CommunicationCreate(CommunicationBase):
    pass


class CommunicationRead(CommunicationBase):
    id: uuid.UUID
    property_id: uuid.UUID
    occurred_at: datetime
    created_at: datetime


# --- Rehab projects ---------------------------------------------------------


class RehabProjectBase(AtlasModel):
    estimated_rehab: Optional[Decimal] = Field(default=None, ge=0)
    actual_rehab: Optional[Decimal] = Field(default=None, ge=0)
    materials_cost: Optional[Decimal] = Field(default=None, ge=0)
    labor_cost: Optional[Decimal] = Field(default=None, ge=0)
    contractors: Optional[Dict[str, Any]] = None
    scope: Optional[str] = Field(default=None, max_length=20_000)
    start_date: Optional[date] = None
    completion_date: Optional[date] = None
    status: str = Field(default="planned", max_length=40)
    notes: Optional[str] = Field(default=None, max_length=20_000)


class RehabProjectCreate(RehabProjectBase):
    pass


class RehabProjectRead(RehabProjectBase):
    id: uuid.UUID
    property_id: uuid.UUID
    variance: Optional[Decimal] = None
    created_at: datetime


# --- Analysis ---------------------------------------------------------------


class EvidencePayload(AtlasModel):
    arv_basis: str = "unknown"
    comp_count: int = Field(default=0, ge=0, le=1000)
    average_comp_similarity: Optional[Decimal] = Field(default=None, ge=0, le=1)
    average_comp_age_days: Optional[int] = Field(default=None, ge=0)
    rehab_basis: str = "unknown"
    rent_basis: str = "unknown"
    inspection_completed: bool = False
    title_reviewed: bool = False
    property_visited: bool = False


class PropertyFactsPayload(AtlasModel):
    address: Optional[str] = Field(default=None, max_length=300)
    city: Optional[str] = Field(default=None, max_length=120)
    state: Optional[str] = Field(default=None, max_length=2)
    zip_code: Optional[str] = Field(default=None, max_length=12)
    county: Optional[str] = Field(default=None, max_length=120)
    property_type: Optional[str] = Field(default=None, max_length=50)
    bedrooms: Optional[Decimal] = Field(default=None, ge=0, le=100)
    bathrooms: Optional[Decimal] = Field(default=None, ge=0, le=100)
    square_feet: Optional[Decimal] = Field(default=None, ge=0)
    lot_size: Optional[Decimal] = Field(default=None, ge=0)
    year_built: Optional[int] = Field(default=None, ge=1600, le=2100)
    occupancy: Optional[str] = Field(default=None, max_length=40)


class AnalysisRequest(AtlasModel):
    """Input to the deal analyzer.

    Every field is optional. The engine reports what it cannot compute rather
    than refusing to run, so a half-filled form still returns useful analysis.
    """

    purchase_price: Optional[Decimal] = Field(default=None, ge=0, le=1_000_000_000)
    arv: Optional[Decimal] = Field(default=None, ge=0, le=1_000_000_000)
    arv_low: Optional[Decimal] = Field(default=None, ge=0, le=1_000_000_000)
    arv_high: Optional[Decimal] = Field(default=None, ge=0, le=1_000_000_000)
    rehab: Optional[Decimal] = Field(default=None, ge=0, le=1_000_000_000)
    rehab_low: Optional[Decimal] = Field(default=None, ge=0, le=1_000_000_000)
    rehab_high: Optional[Decimal] = Field(default=None, ge=0, le=1_000_000_000)
    monthly_rent: Optional[Decimal] = Field(default=None, ge=0, le=10_000_000)
    as_is_value: Optional[Decimal] = Field(default=None, ge=0, le=1_000_000_000)
    listing_price: Optional[Decimal] = Field(default=None, ge=0, le=1_000_000_000)

    property_facts: Optional[PropertyFactsPayload] = None
    evidence: Optional[EvidencePayload] = None
    # Partial assumption overrides; anything omitted keeps its default.
    assumptions: Optional[Dict[str, Any]] = None
    risk_flags: List[str] = Field(default_factory=list, max_length=50)

    # Ask the AI layer to narrate the result. Off by default: the numbers are
    # the product, and the AI call costs time and money.
    include_ai: bool = False

    @field_validator("risk_flags")
    @classmethod
    def _bounded_flags(cls, v: List[str]) -> List[str]:
        for flag in v:
            if len(flag) > 60:
                raise ValueError("risk flag codes must be 60 characters or fewer")
        return v


class SaveAnalysisRequest(AnalysisRequest):
    """An analysis request plus where to save it and why it changed."""

    name: Optional[str] = Field(default=None, max_length=200)
    change_reason: Optional[str] = Field(default=None, max_length=2000)


class AnalysisResponse(AtlasModel):
    """The complete analysis. Deliberately a passthrough of engine output."""

    id: Optional[uuid.UUID] = None
    property_id: Optional[uuid.UUID] = None
    name: Optional[str] = None
    inputs: Dict[str, Any]
    strategies: Dict[str, Any]
    ranking: List[Dict[str, Any]]
    recommended_strategy: Optional[str]
    alternative_strategy: Optional[str]
    rationale: List[str]
    viable_exit_count: int
    overall_confidence: str
    missing_information: List[str]
    scoring: Dict[str, Any]
    ai_analysis: Optional[Dict[str, Any]] = None
    engine_version: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AnalysisSummary(AtlasModel):
    id: uuid.UUID
    property_id: uuid.UUID
    name: Optional[str] = None
    recommended_strategy: Optional[str] = None
    verdict: Optional[str] = None
    deal_score: Optional[Decimal] = None
    profit: Optional[Decimal] = None
    cash_required: Optional[Decimal] = None
    monthly_cash_flow: Optional[Decimal] = None
    confidence: Optional[str] = None
    requires_human_review: bool = False
    created_at: datetime
    updated_at: datetime


class AssumptionAuditRead(AtlasModel):
    id: uuid.UUID
    analysis_id: uuid.UUID
    field_path: str
    field_label: Optional[str] = None
    previous_value: Optional[str] = None
    new_value: Optional[str] = None
    reason: Optional[str] = None
    changed_by: uuid.UUID
    changed_by_email: Optional[str] = None
    changed_at: datetime


# --- Settings ---------------------------------------------------------------


class UserSettingsRead(AtlasModel):
    id: uuid.UUID
    email: Optional[str] = None
    display_name: Optional[str] = None
    default_assumptions: Dict[str, Any]
    provisional_defaults_note: str


class UserSettingsUpdate(AtlasModel):
    display_name: Optional[str] = Field(default=None, max_length=200)
    default_assumptions: Optional[Dict[str, Any]] = None


# --- Dashboard --------------------------------------------------------------


class ActivityRead(AtlasModel):
    id: uuid.UUID
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[uuid.UUID] = None
    summary: Optional[str] = None
    occurred_at: datetime


class PipelineBucket(AtlasModel):
    status: str
    count: int


class DashboardResponse(AtlasModel):
    property_count: int
    analyzed_count: int
    pipeline: List[PipelineBucket]
    top_opportunities: List[PropertySummary]
    needs_human_review: List[PropertySummary]
    projected_wholesale_revenue: Decimal
    projected_flip_profit: Decimal
    projected_monthly_cash_flow: Decimal
    portfolio_equity: Decimal
    follow_ups: List[CommunicationRead]
    recent_activity: List[ActivityRead]


# --- Provider / AI status ---------------------------------------------------


class ProviderStatus(AtlasModel):
    name: str
    configured: bool
    capabilities: List[str]
    detail: str


class SystemStatus(AtlasModel):
    status: str
    environment: str
    engine_version: str
    database: str
    authentication: str
    ai_provider: ProviderStatus
    data_providers: List[ProviderStatus]
