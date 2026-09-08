"""Deal analyzer and saved analyses.

``POST /api/analyze`` is stateless: it underwrites a set of numbers and returns
the result without touching the database. It is what makes the UI's assumptions
update live — the user changes a field, the engine recomputes, nothing is
saved until they ask for it.

Saving goes through the property-scoped endpoints, which additionally write the
assumption audit trail.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..auth import CurrentUser, get_current_user
from ..config import Settings, get_settings
from ..db import get_db
from ..deps import get_owned_analysis, get_owned_property, user_default_assumptions
from ..models import AssumptionAudit, DealAnalysis, Property
from ..schemas import (
    AnalysisRequest,
    AnalysisResponse,
    AnalysisSummary,
    AssumptionAuditRead,
    SaveAnalysisRequest,
)
from ..services.analysis import (
    apply_to_model,
    build_deal_inputs,
    build_response_payload,
    run_analysis,
    stored_analysis_payload,
)
from ..services.audit import log_activity, record_assumption_changes

logger = logging.getLogger("atlas.api.analyses")

router = APIRouter(tags=["analysis"])


@router.post("/analyze", response_model=AnalysisResponse)
def analyze(
    request: AnalysisRequest,
    user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    defaults: Optional[Dict[str, Any]] = Depends(user_default_assumptions),
) -> AnalysisResponse:
    """Underwrite a set of numbers without saving anything.

    Every strategy is evaluated. Strategies that cannot be computed come back
    marked not viable with the reason and the missing fields, rather than
    silently returning zeros.
    """
    inputs = build_deal_inputs(request.model_dump(exclude={"include_ai"}), defaults)
    comparison, scoring, ai_output = run_analysis(inputs, request.include_ai, settings)
    return AnalysisResponse(**build_response_payload(inputs, comparison, scoring, ai_output))


@router.post(
    "/properties/{property_id}/analyses",
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_analysis(
    request: SaveAnalysisRequest,
    property_row: Property = Depends(get_owned_property),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    defaults: Optional[Dict[str, Any]] = Depends(user_default_assumptions),
) -> AnalysisResponse:
    """Run and save an analysis against a property."""
    payload = request.model_dump(exclude={"include_ai", "name", "change_reason"})
    inputs = build_deal_inputs(payload, defaults, property_row)
    comparison, scoring, ai_output = run_analysis(inputs, request.include_ai, settings)

    analysis = DealAnalysis(
        property_id=property_row.id,
        owner_id=user.id,
        name=request.name or "Analysis",
    )
    apply_to_model(analysis, inputs, comparison, scoring, ai_output)
    db.add(analysis)
    db.flush()

    # The first save records the starting assumptions, so the trail is complete
    # from the beginning rather than starting at the first edit.
    record_assumption_changes(
        db, analysis, user, previous_inputs=None, current_inputs=analysis.inputs_json,
        reason=request.change_reason or "Initial analysis",
    )
    log_activity(
        db,
        user,
        "analysis.created",
        "deal_analysis",
        analysis.id,
        f"{scoring.verdict.value} — {analysis.recommended_strategy or 'no strategy'}",
    )
    db.commit()
    db.refresh(analysis)

    response = build_response_payload(inputs, comparison, scoring, ai_output)
    response.update(
        id=analysis.id,
        property_id=analysis.property_id,
        name=analysis.name,
        created_at=analysis.created_at,
        updated_at=analysis.updated_at,
    )
    return AnalysisResponse(**response)


@router.get("/properties/{property_id}/analyses", response_model=List[AnalysisSummary])
def list_analyses(
    property_row: Property = Depends(get_owned_property),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
) -> List[AnalysisSummary]:
    rows = db.execute(
        select(DealAnalysis)
        .where(DealAnalysis.property_id == property_row.id)
        .order_by(desc(DealAnalysis.created_at))
        .limit(limit)
    ).scalars().all()
    return [AnalysisSummary.model_validate(row) for row in rows]


@router.get("/analyses/{analysis_id}", response_model=AnalysisResponse)
def get_analysis(analysis: DealAnalysis = Depends(get_owned_analysis)) -> AnalysisResponse:
    """Reopen a saved analysis.

    Returns exactly what was stored rather than recomputing, so an analysis
    reads the same months later even if the engine's defaults have moved on.
    """
    return AnalysisResponse(**stored_analysis_payload(analysis))


@router.put("/analyses/{analysis_id}", response_model=AnalysisResponse)
def update_analysis(
    request: SaveAnalysisRequest,
    analysis: DealAnalysis = Depends(get_owned_analysis),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    defaults: Optional[Dict[str, Any]] = Depends(user_default_assumptions),
) -> AnalysisResponse:
    """Re-underwrite a saved analysis, recording what changed and why."""
    property_row = db.get(Property, analysis.property_id)
    previous_inputs = analysis.inputs_json

    payload = request.model_dump(exclude={"include_ai", "name", "change_reason"})
    inputs = build_deal_inputs(payload, defaults, property_row)
    comparison, scoring, ai_output = run_analysis(inputs, request.include_ai, settings)

    if request.name:
        analysis.name = request.name
    apply_to_model(analysis, inputs, comparison, scoring, ai_output)

    changes = record_assumption_changes(
        db, analysis, user, previous_inputs, analysis.inputs_json, request.change_reason
    )
    log_activity(
        db,
        user,
        "analysis.updated",
        "deal_analysis",
        analysis.id,
        f"{len(changes)} assumption(s) changed",
    )
    db.commit()
    db.refresh(analysis)

    response = build_response_payload(inputs, comparison, scoring, ai_output)
    response.update(
        id=analysis.id,
        property_id=analysis.property_id,
        name=analysis.name,
        created_at=analysis.created_at,
        updated_at=analysis.updated_at,
    )
    return AnalysisResponse(**response)


@router.delete("/analyses/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_analysis(
    analysis: DealAnalysis = Depends(get_owned_analysis),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> None:
    log_activity(db, user, "analysis.deleted", "deal_analysis", analysis.id, analysis.name)
    db.delete(analysis)
    db.commit()


@router.get("/analyses/{analysis_id}/audit", response_model=List[AssumptionAuditRead])
def get_audit_trail(
    analysis: DealAnalysis = Depends(get_owned_analysis),
    db: Session = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=1000),
) -> List[AssumptionAuditRead]:
    """Every recorded change to this analysis's assumptions, newest first."""
    rows = db.execute(
        select(AssumptionAudit)
        .where(AssumptionAudit.analysis_id == analysis.id)
        .order_by(desc(AssumptionAudit.changed_at))
        .limit(limit)
    ).scalars().all()
    return [AssumptionAuditRead.model_validate(row) for row in rows]


@router.post("/analyses/{analysis_id}/ai", response_model=AnalysisResponse)
def generate_ai_analysis(
    analysis: DealAnalysis = Depends(get_owned_analysis),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    defaults: Optional[Dict[str, Any]] = Depends(user_default_assumptions),
) -> AnalysisResponse:
    """Add AI narration to a saved analysis, re-running the engine unchanged."""
    if not analysis.inputs_json:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This analysis has no stored inputs to interpret.",
        )
    property_row = db.get(Property, analysis.property_id)
    inputs = build_deal_inputs(analysis.inputs_json, None, property_row)
    comparison, scoring, ai_output = run_analysis(inputs, include_ai=True, settings=settings)

    analysis.ai_analysis_json = ai_output
    log_activity(db, user, "analysis.ai_generated", "deal_analysis", analysis.id)
    db.commit()
    db.refresh(analysis)

    response = build_response_payload(inputs, comparison, scoring, ai_output)
    response.update(
        id=analysis.id,
        property_id=analysis.property_id,
        name=analysis.name,
        created_at=analysis.created_at,
        updated_at=analysis.updated_at,
    )
    return AnalysisResponse(**response)
