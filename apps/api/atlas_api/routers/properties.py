"""Properties and their related records."""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..auth import CurrentUser, get_current_user
from ..config import Settings, get_settings
from ..db import get_db
from ..deps import get_owned_property
from ..models import (
    Comp,
    Communication,
    DataSource,
    DealAnalysis,
    Lead,
    Offer,
    Owner,
    Property,
    RehabProject,
)
from ..schemas import (
    CommunicationCreate,
    CommunicationRead,
    CompCreate,
    CompRead,
    OfferCreate,
    OfferRead,
    OwnerCreate,
    OwnerRead,
    PropertyCreate,
    PropertyRead,
    PropertySummary,
    PropertyUpdate,
    RehabProjectCreate,
    RehabProjectRead,
)
from ..services.audit import log_activity

logger = logging.getLogger("atlas.api.properties")

router = APIRouter(prefix="/properties", tags=["properties"])


def _latest_analysis(db: Session, property_id: uuid.UUID) -> Optional[DealAnalysis]:
    return db.execute(
        select(DealAnalysis)
        .where(DealAnalysis.property_id == property_id)
        .order_by(desc(DealAnalysis.created_at))
        .limit(1)
    ).scalar_one_or_none()


def _summarise(db: Session, row: Property) -> PropertySummary:
    latest = _latest_analysis(db, row.id)
    return PropertySummary(
        id=row.id,
        address=row.address,
        city=row.city,
        state=row.state,
        zip_code=row.zip_code,
        property_type=row.property_type,
        property_status=row.property_status,
        bedrooms=row.bedrooms,
        bathrooms=row.bathrooms,
        square_feet=row.square_feet,
        estimated_value=row.estimated_value,
        updated_at=row.updated_at,
        latest_analysis_id=latest.id if latest else None,
        deal_score=latest.deal_score if latest else None,
        verdict=latest.verdict if latest else None,
        recommended_strategy=latest.recommended_strategy if latest else None,
        profit=latest.profit if latest else None,
        cash_required=latest.cash_required if latest else None,
        confidence=latest.confidence if latest else None,
        requires_human_review=bool(latest.requires_human_review) if latest else False,
    )


@router.get("", response_model=List[PropertySummary])
def list_properties(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    search: Optional[str] = Query(default=None, max_length=200),
    state: Optional[str] = Query(default=None, min_length=2, max_length=2),
    property_status: Optional[str] = Query(default=None, max_length=40),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> List[PropertySummary]:
    query = select(Property).where(Property.owner_id == user.id)
    if search:
        pattern = f"%{search.lower()}%"
        query = query.where(
            func.lower(Property.address).like(pattern) | func.lower(Property.city).like(pattern)
        )
    if state:
        query = query.where(Property.state == state.upper())
    if property_status:
        query = query.where(Property.property_status == property_status)
    rows = db.execute(
        query.order_by(desc(Property.updated_at)).limit(limit).offset(offset)
    ).scalars().all()
    return [_summarise(db, row) for row in rows]


@router.post("", response_model=PropertyRead, status_code=status.HTTP_201_CREATED)
def create_property(
    payload: PropertyCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> PropertyRead:
    row = Property(owner_id=user.id, **payload.model_dump())
    db.add(row)
    db.flush()
    log_activity(db, user, "property.created", "property", row.id, row.address)
    db.commit()
    db.refresh(row)
    return PropertyRead.model_validate(row)


@router.get("/{property_id}", response_model=PropertyRead)
def get_property(row: Property = Depends(get_owned_property)) -> PropertyRead:
    return PropertyRead.model_validate(row)


@router.patch("/{property_id}", response_model=PropertyRead)
def update_property(
    payload: PropertyUpdate,
    row: Property = Depends(get_owned_property),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> PropertyRead:
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(row, field, value)
    log_activity(
        db,
        user,
        "property.updated",
        "property",
        row.id,
        f"changed: {', '.join(sorted(changes)) or 'nothing'}",
    )
    db.commit()
    db.refresh(row)
    return PropertyRead.model_validate(row)


@router.delete("/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_property(
    row: Property = Depends(get_owned_property),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> None:
    log_activity(db, user, "property.deleted", "property", row.id, row.address)
    db.delete(row)
    db.commit()


# --- Owners -----------------------------------------------------------------


@router.get("/{property_id}/owners", response_model=List[OwnerRead])
def list_owners(
    row: Property = Depends(get_owned_property), db: Session = Depends(get_db)
) -> List[OwnerRead]:
    rows = db.execute(select(Owner).where(Owner.property_id == row.id)).scalars().all()
    return [OwnerRead.model_validate(r) for r in rows]


@router.post(
    "/{property_id}/owners", response_model=OwnerRead, status_code=status.HTTP_201_CREATED
)
def create_owner(
    payload: OwnerCreate,
    row: Property = Depends(get_owned_property),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> OwnerRead:
    owner = Owner(property_id=row.id, **payload.model_dump())
    db.add(owner)
    db.flush()
    # Deliberately no owner name in the log summary.
    log_activity(db, user, "owner.created", "owner", owner.id)
    db.commit()
    db.refresh(owner)
    return OwnerRead.model_validate(owner)


# --- Comps ------------------------------------------------------------------


@router.get("/{property_id}/comps", response_model=List[CompRead])
def list_comps(
    row: Property = Depends(get_owned_property), db: Session = Depends(get_db)
) -> List[CompRead]:
    rows = db.execute(
        select(Comp)
        .where(Comp.property_id == row.id)
        .order_by(desc(Comp.similarity_score))
    ).scalars().all()
    return [CompRead.model_validate(r) for r in rows]


@router.post(
    "/{property_id}/comps", response_model=CompRead, status_code=status.HTTP_201_CREATED
)
def create_comp(
    payload: CompCreate,
    row: Property = Depends(get_owned_property),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> CompRead:
    comp = Comp(property_id=row.id, **payload.model_dump())
    db.add(comp)
    db.flush()
    log_activity(db, user, "comp.created", "comp", comp.id)
    db.commit()
    db.refresh(comp)
    return CompRead.model_validate(comp)


@router.delete("/{property_id}/comps/{comp_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comp(
    comp_id: uuid.UUID,
    row: Property = Depends(get_owned_property),
    db: Session = Depends(get_db),
) -> None:
    comp = db.execute(
        select(Comp).where(Comp.id == comp_id, Comp.property_id == row.id)
    ).scalar_one_or_none()
    if comp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comp not found.")
    db.delete(comp)
    db.commit()


# --- Offers -----------------------------------------------------------------


@router.get("/{property_id}/offers", response_model=List[OfferRead])
def list_offers(
    row: Property = Depends(get_owned_property), db: Session = Depends(get_db)
) -> List[OfferRead]:
    rows = db.execute(
        select(Offer).where(Offer.property_id == row.id).order_by(desc(Offer.created_at))
    ).scalars().all()
    return [OfferRead.model_validate(r) for r in rows]


@router.post(
    "/{property_id}/offers", response_model=OfferRead, status_code=status.HTTP_201_CREATED
)
def create_offer(
    payload: OfferCreate,
    row: Property = Depends(get_owned_property),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> OfferRead:
    offer = Offer(property_id=row.id, owner_id=user.id, **payload.model_dump())
    db.add(offer)
    db.flush()
    log_activity(
        db, user, "offer.created", "offer", offer.id, f"${offer.offer_amount:,.0f}"
    )
    db.commit()
    db.refresh(offer)
    return OfferRead.model_validate(offer)


# --- Communications ---------------------------------------------------------


@router.get("/{property_id}/communications", response_model=List[CommunicationRead])
def list_communications(
    row: Property = Depends(get_owned_property), db: Session = Depends(get_db)
) -> List[CommunicationRead]:
    rows = db.execute(
        select(Communication)
        .where(Communication.property_id == row.id)
        .order_by(desc(Communication.occurred_at))
    ).scalars().all()
    return [CommunicationRead.model_validate(r) for r in rows]


@router.post(
    "/{property_id}/communications",
    response_model=CommunicationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_communication(
    payload: CommunicationCreate,
    row: Property = Depends(get_owned_property),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> CommunicationRead:
    data = payload.model_dump(exclude_none=True)
    record = Communication(property_id=row.id, owner_id=user.id, **data)
    db.add(record)
    db.flush()
    log_activity(
        db, user, "communication.logged", "communication", record.id, record.communication_type
    )
    db.commit()
    db.refresh(record)
    return CommunicationRead.model_validate(record)


# --- Rehab projects ---------------------------------------------------------


@router.get("/{property_id}/rehab-projects", response_model=List[RehabProjectRead])
def list_rehab_projects(
    row: Property = Depends(get_owned_property), db: Session = Depends(get_db)
) -> List[RehabProjectRead]:
    rows = db.execute(
        select(RehabProject).where(RehabProject.property_id == row.id)
    ).scalars().all()
    return [
        RehabProjectRead.model_validate(r).model_copy(update={"variance": r.variance})
        for r in rows
    ]


@router.post(
    "/{property_id}/rehab-projects",
    response_model=RehabProjectRead,
    status_code=status.HTTP_201_CREATED,
)
def create_rehab_project(
    payload: RehabProjectCreate,
    row: Property = Depends(get_owned_property),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> RehabProjectRead:
    project = RehabProject(property_id=row.id, owner_id=user.id, **payload.model_dump())
    db.add(project)
    db.flush()
    log_activity(db, user, "rehab_project.created", "rehab_project", project.id)
    db.commit()
    db.refresh(project)
    return RehabProjectRead.model_validate(project).model_copy(
        update={"variance": project.variance}
    )


# --- Data provider enrichment ----------------------------------------------


@router.post("/{property_id}/enrich")
def enrich_property(
    row: Property = Depends(get_owned_property),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Pull external data for this property, if a provider is configured.

    Every imported value is written to ``data_sources`` with its provenance, so
    the origin of each field is recoverable later. With no provider configured
    this returns a clear "not connected" result rather than an error — manual
    entry is a supported way to run Atlas.
    """
    from atlas_data_providers import ProviderError, get_provider

    provider = get_provider(
        "rentcast" if settings.rentcast_api_key else "none",
        api_key=settings.rentcast_api_key,
        base_url=settings.rentcast_base_url,
    )
    if provider.name == "none":
        return {
            "provider": "none",
            "imported": [],
            "unavailable": ["no data provider configured"],
            "detail": (
                "No property data provider is connected. Atlas works normally with "
                "manually entered data."
            ),
        }

    try:
        lookup = provider.lookup(row.address)
    except ProviderError as exc:
        logger.info("enrichment unavailable for %s: %s", row.id, exc)
        return {
            "provider": provider.name,
            "imported": [],
            "unavailable": ["provider request failed"],
            "detail": str(exc),
        }

    imported: List[str] = []

    def record(field: str, value, provenance) -> None:
        db.add(
            DataSource(
                property_id=row.id,
                provider=provenance.provider if provenance else provider.name,
                provider_record_id=provenance.provider_record_id if provenance else None,
                field_name=field,
                field_value=str(value)[:400],
                source_url=provenance.source_url if provenance else None,
                confidence=provenance.confidence if provenance else None,
            )
        )
        imported.append(field)

    if lookup.property:
        for field in (
            "city",
            "state",
            "zip_code",
            "county",
            "parcel_apn",
            "property_type",
            "bedrooms",
            "bathrooms",
            "square_feet",
            "lot_size",
            "year_built",
            "latitude",
            "longitude",
        ):
            value = getattr(lookup.property, field, None)
            # Never overwrite something a person entered by hand.
            if value is not None and getattr(row, field, None) is None:
                setattr(row, field, value)
                record(field, value, lookup.property.provenance)

    if lookup.value and lookup.value.value is not None and row.estimated_value is None:
        row.estimated_value = lookup.value.value
        record("estimated_value", lookup.value.value, lookup.value.provenance)

    if lookup.rent and lookup.rent.rent is not None and row.estimated_rent is None:
        row.estimated_rent = lookup.rent.rent
        record("estimated_rent", lookup.rent.rent, lookup.rent.provenance)

    for comp in lookup.comps:
        db.add(
            Comp(
                property_id=row.id,
                address=comp.address or "unknown",
                distance_miles=comp.distance_miles,
                sale_price=comp.sale_price,
                sale_date=comp.sale_date,
                bedrooms=comp.bedrooms,
                bathrooms=comp.bathrooms,
                square_feet=comp.square_feet,
                lot_size=comp.lot_size,
                year_built=comp.year_built,
                property_type=comp.property_type,
                price_per_square_foot=comp.price_per_square_foot,
                similarity_score=comp.similarity_score,
                source=provider.name,
            )
        )

    log_activity(
        db, user, "property.enriched", "property", row.id, f"{len(imported)} field(s)"
    )
    db.commit()
    db.refresh(row)
    return {
        "provider": provider.name,
        "imported": imported,
        "comps_imported": len(lookup.comps),
        "unavailable": lookup.unavailable,
        "detail": "Imported fields are recorded with provenance in data_sources.",
    }
