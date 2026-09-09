"""Shared dependencies.

The authorization rule for the whole API lives here: a record is reachable only
by the user who owns it. ``get_owned_property`` returns 404 rather than 403 for
someone else's property, so the API does not confirm that an id exists to a
caller with no right to know.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import CurrentUser, get_current_user
from .db import get_db
from .models import DealAnalysis, Property, UserProfile


def get_owned_property(
    property_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> Property:
    row = db.execute(
        select(Property).where(
            Property.id == property_id, Property.owner_id == user.id
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Property not found."
        )
    return row


def get_owned_analysis(
    analysis_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> DealAnalysis:
    row = db.execute(
        select(DealAnalysis).where(
            DealAnalysis.id == analysis_id, DealAnalysis.owner_id == user.id
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found."
        )
    return row


def get_or_create_profile(db: Session, user: CurrentUser) -> UserProfile:
    profile = db.get(UserProfile, user.id)
    if profile is None:
        profile = UserProfile(id=user.id, email=user.email)
        db.add(profile)
        db.flush()
    return profile


def user_default_assumptions(
    db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
) -> Optional[Dict[str, Any]]:
    profile = db.get(UserProfile, user.id)
    return profile.default_assumptions if profile else None


def user_investor_profile(
    db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
) -> Optional[Dict[str, Any]]:
    """The investor's saved capital constraints and return requirements.

    Separate from the buy box: one describes the investor, the other the deal.
    """
    profile = db.get(UserProfile, user.id)
    return profile.investor_profile if profile else None
