"""User settings — the buy box.

Saved assumptions here become the starting point for every new analysis. They
are still provisional defaults, and any deal can override them; that override
is what the audit trail records.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from atlas_financial_engine import Assumptions
from atlas_financial_engine.assumptions import PROVISIONAL_DEFAULTS_NOTE

from ..auth import CurrentUser, get_current_user
from ..db import get_db
from ..deps import get_or_create_profile
from ..schemas import UserSettingsRead, UserSettingsUpdate
from ..services.analysis import resolve_assumptions
from ..services.audit import log_activity

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=UserSettingsRead)
def get_settings_for_user(
    db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
) -> UserSettingsRead:
    profile = get_or_create_profile(db, user)
    db.commit()
    assumptions = resolve_assumptions(profile.default_assumptions, None)
    return UserSettingsRead(
        id=profile.id,
        email=profile.email,
        display_name=profile.display_name,
        default_assumptions=assumptions.to_dict(),
        provisional_defaults_note=PROVISIONAL_DEFAULTS_NOTE,
    )


@router.put("", response_model=UserSettingsRead)
def update_settings(
    payload: UserSettingsUpdate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> UserSettingsRead:
    profile = get_or_create_profile(db, user)

    if payload.display_name is not None:
        profile.display_name = payload.display_name

    if payload.default_assumptions is not None:
        # Round-trip through the engine so an invalid buy box is rejected here
        # rather than silently breaking every future analysis.
        try:
            validated = Assumptions.from_dict(payload.default_assumptions)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid assumptions: {exc}",
            ) from exc
        profile.default_assumptions = validated.to_dict()

    log_activity(db, user, "settings.updated", "user_profile", profile.id)
    db.commit()
    db.refresh(profile)

    return UserSettingsRead(
        id=profile.id,
        email=profile.email,
        display_name=profile.display_name,
        default_assumptions=resolve_assumptions(profile.default_assumptions, None).to_dict(),
        provisional_defaults_note=PROVISIONAL_DEFAULTS_NOTE,
    )


@router.post("/reset", response_model=UserSettingsRead)
def reset_settings(
    db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
) -> UserSettingsRead:
    """Restore the engine's provisional defaults."""
    profile = get_or_create_profile(db, user)
    profile.default_assumptions = None
    log_activity(db, user, "settings.reset", "user_profile", profile.id)
    db.commit()
    return UserSettingsRead(
        id=profile.id,
        email=profile.email,
        display_name=profile.display_name,
        default_assumptions=Assumptions().to_dict(),
        provisional_defaults_note=PROVISIONAL_DEFAULTS_NOTE,
    )
