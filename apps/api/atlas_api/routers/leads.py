"""Leads.

``lead_type`` records how a property came to attention — FSBO, vacant,
absentee, long days-on-market. These are classifications of an observable
situation. Atlas does not treat any of them as evidence that an owner wants to
sell, and no endpoint here scores or ranks a lead by inferred motivation.
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..auth import CurrentUser, get_current_user
from ..db import get_db
from ..models import Lead, Property
from ..schemas import LeadCreate, LeadRead, LeadUpdate
from ..services.audit import log_activity

router = APIRouter(prefix="/leads", tags=["leads"])


@router.get("", response_model=List[LeadRead])
def list_leads(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    lead_type: Optional[str] = Query(default=None, max_length=40),
    lead_status: Optional[str] = Query(default=None, alias="status", max_length=40),
    limit: int = Query(default=100, ge=1, le=500),
) -> List[LeadRead]:
    query = select(Lead).where(Lead.owner_id == user.id)
    if lead_type:
        query = query.where(Lead.lead_type == lead_type)
    if lead_status:
        query = query.where(Lead.status == lead_status)
    rows = db.execute(
        query.order_by(desc(Lead.updated_at)).limit(limit)
    ).scalars().all()
    return [LeadRead.model_validate(r) for r in rows]


@router.post("", response_model=LeadRead, status_code=status.HTTP_201_CREATED)
def create_lead(
    payload: LeadCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> LeadRead:
    property_row = db.execute(
        select(Property).where(
            Property.id == payload.property_id, Property.owner_id == user.id
        )
    ).scalar_one_or_none()
    if property_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Property not found."
        )

    lead = Lead(owner_id=user.id, **payload.model_dump())
    db.add(lead)
    db.flush()
    log_activity(db, user, "lead.created", "lead", lead.id, lead.lead_type)
    db.commit()
    db.refresh(lead)
    return LeadRead.model_validate(lead)


@router.patch("/{lead_id}", response_model=LeadRead)
def update_lead(
    lead_id: uuid.UUID,
    payload: LeadUpdate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> LeadRead:
    lead = db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.owner_id == user.id)
    ).scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(lead, field, value)
    log_activity(db, user, "lead.updated", "lead", lead.id, lead.status)
    db.commit()
    db.refresh(lead)
    return LeadRead.model_validate(lead)


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lead(
    lead_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> None:
    lead = db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.owner_id == user.id)
    ).scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    db.delete(lead)
    db.commit()
