"""Dashboard and system status."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from atlas_financial_engine import __version__ as engine_version

from ..auth import CurrentUser, get_current_user
from ..config import Settings, get_settings
from ..db import get_db
from ..models import ActivityLog, Communication, DealAnalysis, Property
from ..routers.properties import _summarise
from ..schemas import (
    ActivityRead,
    CommunicationRead,
    DashboardResponse,
    PipelineBucket,
    ProviderStatus,
    SystemStatus,
)

router = APIRouter(tags=["dashboard"])

ZERO = Decimal("0")


def _latest_analysis_ids(db: Session, user_id) -> List:
    """One analysis per property: the most recent.

    Older analyses of the same property must not be double-counted in the
    portfolio totals.
    """
    newest = (
        select(
            DealAnalysis.property_id,
            func.max(DealAnalysis.created_at).label("created_at"),
        )
        .where(DealAnalysis.owner_id == user_id)
        .group_by(DealAnalysis.property_id)
        .subquery()
    )
    return db.execute(
        select(DealAnalysis).join(
            newest,
            (DealAnalysis.property_id == newest.c.property_id)
            & (DealAnalysis.created_at == newest.c.created_at),
        )
    ).scalars().all()


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
) -> DashboardResponse:
    property_count = (
        db.execute(
            select(func.count(Property.id)).where(Property.owner_id == user.id)
        ).scalar_one()
        or 0
    )

    analyses = _latest_analysis_ids(db, user.id)

    pipeline_rows = db.execute(
        select(Property.property_status, func.count(Property.id))
        .where(Property.owner_id == user.id)
        .group_by(Property.property_status)
    ).all()
    pipeline = [PipelineBucket(status=row[0], count=row[1]) for row in pipeline_rows]

    projected_wholesale = ZERO
    projected_flip = ZERO
    projected_cash_flow = ZERO
    portfolio_equity = ZERO
    for analysis in analyses:
        strategies = (analysis.results_json or {}).get("strategies", {})
        recommended = analysis.recommended_strategy

        # Only count the strategy actually recommended for a property. Summing
        # every strategy would count the same house as a flip AND a rental.
        if recommended == "wholesale":
            projected_wholesale += analysis.profit or ZERO
        elif recommended == "flip":
            projected_flip += analysis.profit or ZERO
        elif recommended in ("buy_hold", "brrrr", "seller_finance"):
            projected_cash_flow += analysis.monthly_cash_flow or ZERO
        portfolio_equity += analysis.equity_created or ZERO

    properties = db.execute(
        select(Property).where(Property.owner_id == user.id)
    ).scalars().all()
    summaries = [_summarise(db, p) for p in properties]

    scored = [s for s in summaries if s.deal_score is not None]
    top = sorted(scored, key=lambda s: s.deal_score, reverse=True)[:5]
    review = [s for s in summaries if s.requires_human_review][:10]

    follow_ups = db.execute(
        select(Communication)
        .where(
            Communication.owner_id == user.id,
            Communication.follow_up_at.is_not(None),
        )
        .order_by(Communication.follow_up_at)
        .limit(10)
    ).scalars().all()

    activity = db.execute(
        select(ActivityLog)
        .where(ActivityLog.actor_id == user.id)
        .order_by(desc(ActivityLog.occurred_at))
        .limit(15)
    ).scalars().all()

    return DashboardResponse(
        property_count=property_count,
        analyzed_count=len(analyses),
        pipeline=pipeline,
        top_opportunities=top,
        needs_human_review=review,
        projected_wholesale_revenue=projected_wholesale,
        projected_flip_profit=projected_flip,
        projected_monthly_cash_flow=projected_cash_flow,
        portfolio_equity=portfolio_equity,
        follow_ups=[CommunicationRead.model_validate(f) for f in follow_ups],
        recent_activity=[ActivityRead.model_validate(a) for a in activity],
    )


@router.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "engine_version": engine_version}


@router.get("/status", response_model=SystemStatus)
def system_status(settings: Settings = Depends(get_settings)) -> SystemStatus:
    """What is configured and what is not.

    Never returns a key, only whether one is present.
    """
    from atlas_data_providers import describe_providers

    provider_name = (settings.atlas_ai_provider or "null").lower()
    key_present = {
        "anthropic": bool(settings.anthropic_api_key),
        "openai": bool(settings.openai_api_key),
    }.get(provider_name, provider_name in ("null", "none"))

    ai_status = ProviderStatus(
        name=provider_name,
        configured=bool(key_present),
        capabilities=["research", "underwriting", "strategy"],
        detail=(
            "Deterministic analysis only. Narration is composed from the engine's "
            "own numbers, with no language model involved."
            if provider_name in ("null", "none")
            else (
                f"{provider_name} is configured. The AI interprets computed results; "
                "it never performs the calculations."
                if key_present
                else f"{provider_name} selected but no API key is set. Falling back to "
                "deterministic analysis."
            )
        ),
    )

    return SystemStatus(
        status="ok",
        environment=settings.environment,
        engine_version=engine_version,
        database="postgresql" if not settings.uses_sqlite else "sqlite",
        authentication="supabase" if settings.auth_configured else "development",
        ai_provider=ai_status,
        data_providers=[
            ProviderStatus(**p) for p in describe_providers(settings.rentcast_api_key)
        ],
    )
