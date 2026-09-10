"""Database models.

Design notes that apply throughout:

* Money is ``Numeric(14, 2)`` and rates are ``Numeric(12, 6)``. Floats are
  never used for money anywhere in Atlas, including at rest.
* Nullable means unknown. A null ``estimated_rent`` is a property whose rent
  nobody has estimated — it is not a property that rents for nothing.
* Externally sourced values carry provenance through ``data_sources``.
* ``owner_id`` is the Supabase Auth user id. Every query is scoped by it, so
  one account cannot read another's pipeline.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from atlas_financial_engine.assumptions import ASSUMPTIONS_SCHEMA_VERSION

MONEY = Numeric(14, 2)
RATE = Numeric(12, 6)
SMALL = Numeric(10, 2)

# Most models declare a relationship named ``property``, which shadows the
# builtin decorator inside those class bodies. Aliasing it keeps computed
# attributes usable on the same classes.
computed = property


class Base(DeclarativeBase):
    pass


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        onupdate=_now,
        server_default=func.now(),
        nullable=False,
    )


class UserProfile(Base, TimestampMixin):
    """Mirror of the Supabase Auth user, plus Atlas-specific settings.

    Authentication stays in Supabase; this table only holds what Atlas needs
    (default assumptions, display name). No password material is ever stored.
    """

    __tablename__ = "user_profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    email: Mapped[Optional[str]] = mapped_column(String(320), index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(200))
    # The user's buy box: per-deal underwriting defaults.
    default_assumptions: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    # The investor themselves: capital available, return requirements, risk
    # tolerance. Kept separate from the buy box because it describes the
    # investor rather than any property.
    investor_profile: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)


class Property(Base, TimestampMixin):
    __tablename__ = "properties"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)

    address: Mapped[str] = mapped_column(String(300), nullable=False)
    city: Mapped[Optional[str]] = mapped_column(String(120))
    # Two-letter state code. Atlas is architected nationwide; the initial
    # focus states carry no special handling anywhere in the codebase.
    state: Mapped[Optional[str]] = mapped_column(String(2), index=True)
    zip_code: Mapped[Optional[str]] = mapped_column(String(12), index=True)
    county: Mapped[Optional[str]] = mapped_column(String(120))
    parcel_apn: Mapped[Optional[str]] = mapped_column(String(80), index=True)

    property_type: Mapped[Optional[str]] = mapped_column(String(50))
    bedrooms: Mapped[Optional[Decimal]] = mapped_column(SMALL)
    bathrooms: Mapped[Optional[Decimal]] = mapped_column(SMALL)
    square_feet: Mapped[Optional[Decimal]] = mapped_column(SMALL)
    lot_size: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    year_built: Mapped[Optional[int]] = mapped_column(Integer)

    property_status: Mapped[str] = mapped_column(String(40), default="prospect")
    listing_price: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    estimated_value: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    estimated_rent: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    days_on_market: Mapped[Optional[int]] = mapped_column(Integer)

    latitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 7))

    notes: Mapped[Optional[str]] = mapped_column(Text)

    owners: Mapped[List["Owner"]] = relationship(
        back_populates="property", cascade="all, delete-orphan"
    )
    leads: Mapped[List["Lead"]] = relationship(
        back_populates="property", cascade="all, delete-orphan"
    )
    analyses: Mapped[List["DealAnalysis"]] = relationship(
        back_populates="property", cascade="all, delete-orphan"
    )
    comps: Mapped[List["Comp"]] = relationship(
        back_populates="property", cascade="all, delete-orphan"
    )
    offers: Mapped[List["Offer"]] = relationship(
        back_populates="property", cascade="all, delete-orphan"
    )
    communications: Mapped[List["Communication"]] = relationship(
        back_populates="property", cascade="all, delete-orphan"
    )
    rehab_projects: Mapped[List["RehabProject"]] = relationship(
        back_populates="property", cascade="all, delete-orphan"
    )
    data_sources: Mapped[List["DataSource"]] = relationship(
        back_populates="property", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_properties_owner_state", "owner_id", "state"),)


class Owner(Base, TimestampMixin):
    """Ownership facts.

    Deliberately free of motivation inference. Absentee ownership and high
    equity are classifications of a situation, not evidence that someone wants
    to sell, and Atlas does not let a model or a query pretend otherwise.
    """

    __tablename__ = "owners"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    property_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )

    owner_name: Mapped[Optional[str]] = mapped_column(String(300))
    entity_type: Mapped[Optional[str]] = mapped_column(String(60))
    mailing_address: Mapped[Optional[str]] = mapped_column(String(300))
    ownership_start_date: Mapped[Optional[datetime]] = mapped_column(Date)
    estimated_equity: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    estimated_mortgage: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    # "owner_occupied" | "absentee" | "vacant" | "unknown" — an observation.
    occupancy_indicator: Mapped[Optional[str]] = mapped_column(String(40))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    property: Mapped["Property"] = relationship(back_populates="owners")


class Lead(Base, TimestampMixin):
    """A lead classification.

    ``lead_type`` records how a property came to attention (FSBO, vacant,
    long DOM...). These are classifications, not conclusions about motivation.
    """

    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    property_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)

    lead_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(40), default="new", index=True)
    lead_score: Mapped[Optional[Decimal]] = mapped_column(SMALL)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    property: Mapped["Property"] = relationship(back_populates="leads")


class DealAnalysis(Base, TimestampMixin):
    """A saved underwriting run.

    Stores three things: the denormalised headline numbers (so the dashboard
    can query without deserialising), and the complete inputs, assumptions and
    results as JSON (so an analysis can be reproduced exactly, byte for byte,
    when reopened months later).
    """

    __tablename__ = "deal_analyses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    property_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(200))

    # --- Inputs -------------------------------------------------------------
    purchase_price: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    arv_low: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    arv_high: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    arv_confidence: Mapped[Optional[str]] = mapped_column(String(10))
    rehab_low: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    rehab_high: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    rehab_confidence: Mapped[Optional[str]] = mapped_column(String(10))

    closing_costs: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    holding_costs: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    financing_costs: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    selling_costs: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    miscellaneous_costs: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    total_basis: Mapped[Optional[Decimal]] = mapped_column(MONEY)

    rent: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    vacancy: Mapped[Optional[Decimal]] = mapped_column(RATE)
    management: Mapped[Optional[Decimal]] = mapped_column(RATE)
    maintenance: Mapped[Optional[Decimal]] = mapped_column(RATE)
    capex: Mapped[Optional[Decimal]] = mapped_column(RATE)
    taxes: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    insurance: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    hoa: Mapped[Optional[Decimal]] = mapped_column(MONEY)

    # --- Outputs ------------------------------------------------------------
    monthly_cash_flow: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    annual_cash_flow: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    profit: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    cash_required: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    equity_created: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    deal_score: Mapped[Optional[Decimal]] = mapped_column(SMALL)
    risk_score: Mapped[Optional[Decimal]] = mapped_column(SMALL)
    confidence: Mapped[Optional[str]] = mapped_column(String(10))
    recommended_strategy: Mapped[Optional[str]] = mapped_column(String(40), index=True)
    verdict: Mapped[Optional[str]] = mapped_column(String(30), index=True)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, default=False)

    # --- Full fidelity ------------------------------------------------------
    inputs_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    assumptions_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    results_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    scoring_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    ai_analysis_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    engine_version: Mapped[Optional[str]] = mapped_column(String(20))
    # Which generation of assumption semantics assumptions_json was written
    # under. 0 is the pre-tri-state schema, where a stored 0 for taxes or
    # insurance meant "unfilled" rather than "no tax bill" — the engine reads
    # that back as unknown. Stored as a column as well as inside the blob so
    # legacy analyses can be found with a query rather than a JSON scan.
    assumptions_schema_version: Mapped[int] = mapped_column(
        Integer,
        default=ASSUMPTIONS_SCHEMA_VERSION,
        server_default="0",
        comment=(
            "Generation of assumption semantics for assumptions_json. 0 = pre-tri-state, where a stored 0 for taxes/insurance/HOA meant unknown."
        ),
    )

    property: Mapped["Property"] = relationship(back_populates="analyses")
    audit_entries: Mapped[List["AssumptionAudit"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )


class AssumptionAudit(Base):
    """Audit trail for changed underwriting assumptions.

    Underwriting assumptions change, and the reason a deal looked good in March
    is often that someone quietly moved the ARV. Every change to a material
    assumption is recorded with its previous value, new value, who made it,
    when, and why if a reason was supplied.

    Append-only by convention: nothing in the API updates or deletes these rows.
    """

    __tablename__ = "assumption_audit"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deal_analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    property_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, index=True)
    changed_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    changed_by_email: Mapped[Optional[str]] = mapped_column(String(320))
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now(), nullable=False
    )

    field_path: Mapped[str] = mapped_column(String(200), nullable=False)
    field_label: Mapped[Optional[str]] = mapped_column(String(200))
    previous_value: Mapped[Optional[str]] = mapped_column(String(200))
    new_value: Mapped[Optional[str]] = mapped_column(String(200))
    reason: Mapped[Optional[str]] = mapped_column(Text)

    analysis: Mapped["DealAnalysis"] = relationship(back_populates="audit_entries")


class Comp(Base, TimestampMixin):
    __tablename__ = "comps"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    property_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )

    address: Mapped[str] = mapped_column(String(300), nullable=False)
    distance_miles: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 3))
    sale_price: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    sale_date: Mapped[Optional[datetime]] = mapped_column(Date)
    bedrooms: Mapped[Optional[Decimal]] = mapped_column(SMALL)
    bathrooms: Mapped[Optional[Decimal]] = mapped_column(SMALL)
    square_feet: Mapped[Optional[Decimal]] = mapped_column(SMALL)
    lot_size: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    year_built: Mapped[Optional[int]] = mapped_column(Integer)
    property_type: Mapped[Optional[str]] = mapped_column(String(50))
    condition: Mapped[Optional[str]] = mapped_column(String(50))
    price_per_square_foot: Mapped[Optional[Decimal]] = mapped_column(SMALL)
    # 0..1. Drives the ARV confidence rating.
    similarity_score: Mapped[Optional[Decimal]] = mapped_column(RATE)
    source: Mapped[Optional[str]] = mapped_column(String(80))

    property: Mapped["Property"] = relationship(back_populates="comps")


class Offer(Base, TimestampMixin):
    __tablename__ = "offers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    property_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)

    offer_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    offer_type: Mapped[Optional[str]] = mapped_column(String(50))
    terms: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="draft", index=True)
    date_submitted: Mapped[Optional[datetime]] = mapped_column(Date)
    expiration_date: Mapped[Optional[datetime]] = mapped_column(Date)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    property: Mapped["Property"] = relationship(back_populates="offers")


class Communication(Base, TimestampMixin):
    __tablename__ = "communications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    property_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)

    contact_name: Mapped[Optional[str]] = mapped_column(String(200))
    contact_role: Mapped[Optional[str]] = mapped_column(String(80))
    communication_type: Mapped[str] = mapped_column(String(40), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), default="outbound")
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    notes: Mapped[Optional[str]] = mapped_column(Text)
    outcome: Mapped[Optional[str]] = mapped_column(String(120))
    follow_up_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    property: Mapped["Property"] = relationship(back_populates="communications")


class RehabProject(Base, TimestampMixin):
    """Estimated vs actual rehab.

    The variance recorded here is what will eventually let Atlas learn how
    wrong its own rehab estimates tend to be — the foundation of the
    predictive-intelligence phase.
    """

    __tablename__ = "rehab_projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    property_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)

    estimated_rehab: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    actual_rehab: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    materials_cost: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    labor_cost: Mapped[Optional[Decimal]] = mapped_column(MONEY)
    contractors: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    scope: Mapped[Optional[str]] = mapped_column(Text)
    start_date: Mapped[Optional[datetime]] = mapped_column(Date)
    completion_date: Mapped[Optional[datetime]] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(40), default="planned")
    notes: Mapped[Optional[str]] = mapped_column(Text)

    property: Mapped["Property"] = relationship(back_populates="rehab_projects")

    @computed
    def variance(self) -> Optional[Decimal]:
        if self.actual_rehab is None or self.estimated_rehab is None:
            return None
        return self.actual_rehab - self.estimated_rehab


class DataSource(Base):
    """Provenance for an externally sourced data point.

    Atlas distinguishes fact from estimate, and that distinction is only
    meaningful if the origin of a value is recorded. Every field written by a
    data provider gets a row here.
    """

    __tablename__ = "data_sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    property_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("properties.id", ondelete="CASCADE"), index=True
    )

    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    provider_record_id: Mapped[Optional[str]] = mapped_column(String(200))
    field_name: Mapped[Optional[str]] = mapped_column(String(120))
    field_value: Mapped[Optional[str]] = mapped_column(String(400))
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now(), nullable=False
    )
    source_url: Mapped[Optional[str]] = mapped_column(String(600))
    confidence: Mapped[Optional[str]] = mapped_column(String(10))
    payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)

    property: Mapped[Optional["Property"]] = relationship(back_populates="data_sources")


class ActivityLog(Base):
    """Log of important actions, for security review and recent-activity feeds."""

    __tablename__ = "activity_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, index=True)
    actor_email: Mapped[Optional[str]] = mapped_column(String(320))
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(60))
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, index=True)
    summary: Mapped[Optional[str]] = mapped_column(String(500))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now(), nullable=False, index=True
    )
