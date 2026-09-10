"""Composing an analysis.

This is the seam between the web layer and the engines. It owns three jobs:

1. Turn a validated request into ``DealInputs``, layering the user's saved buy
   box under any per-deal overrides.
2. Run the deterministic engines, then optionally the AI agents.
3. Flatten the result into the denormalised columns the dashboard queries,
   while keeping the full JSON so an analysis reproduces exactly on reopen.

No arithmetic happens here. This module moves data between the engine and the
database and nothing else.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from atlas_ai_agents import get_ai_provider, run_all_agents
from atlas_financial_engine import (
    Assumptions,
    DealInputs,
    InvestorProfile,
    Strategy,
    __version__ as engine_version,
    analyze_all_strategies,
    migrate_assumptions,
)
from atlas_financial_engine.strategy_engine import StrategyComparison
from atlas_scoring_engine import DealScore, score_deal

from ..config import Settings
from ..models import DealAnalysis, Property

logger = logging.getLogger("atlas.analysis")


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Merge override into base, recursing into nested dictionaries.

    A shallow merge would silently discard the rest of a user's flip settings
    when a single field is overridden.
    """
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def resolve_assumptions(
    user_defaults: Optional[Dict[str, Any]],
    request_overrides: Optional[Dict[str, Any]],
) -> Assumptions:
    """Engine defaults < the user's saved buy box < this deal's overrides.

    Each source is brought up to the current assumption schema BEFORE the
    merge, not after. The two can be different generations — a buy box saved
    last year merged with an override typed this morning — and migrating the
    merged result would apply the older source's semantics to the newer one's
    values, turning a deliberate 0 into an unknown.

    A source that does not declare ``schema_version`` is read as legacy; see
    ``migrate_assumptions``. Clients of this API should send the current
    version with any assumptions they set.
    """
    merged: Dict[str, Any] = {}
    for source in (user_defaults, request_overrides):
        if source:
            merged = _deep_merge(merged, dict(migrate_assumptions(source)))
    return Assumptions.from_dict(merged) if merged else Assumptions()


def resolve_investor_profile(
    saved_profile: Optional[Dict[str, Any]],
    request_overrides: Optional[Dict[str, Any]],
) -> InvestorProfile:
    """The investor's saved profile, with any per-analysis override applied.

    Kept separate from ``resolve_assumptions`` because the two describe
    different things: one the investor, the other the deal.
    """
    merged: Dict[str, Any] = {}
    if saved_profile:
        merged = _deep_merge(merged, saved_profile)
    if request_overrides:
        merged = _deep_merge(merged, request_overrides)
    return InvestorProfile.from_dict(merged) if merged else InvestorProfile()


def build_deal_inputs(
    payload: Dict[str, Any],
    user_defaults: Optional[Dict[str, Any]] = None,
    property_row: Optional[Property] = None,
    investor_profile: Optional[Dict[str, Any]] = None,
) -> DealInputs:
    """Build engine inputs from a request payload.

    Property attributes fall back to the stored property record, so an analyzer
    request does not have to restate what Atlas already knows.
    """
    data = dict(payload)
    assumptions = resolve_assumptions(user_defaults, data.pop("assumptions", None))
    profile = resolve_investor_profile(investor_profile, data.pop("investor_profile", None))

    facts = dict(data.pop("property_facts", None) or {})
    if property_row is not None:
        for field, value in (
            ("address", property_row.address),
            ("city", property_row.city),
            ("state", property_row.state),
            ("zip_code", property_row.zip_code),
            ("county", property_row.county),
            ("property_type", property_row.property_type),
            ("bedrooms", property_row.bedrooms),
            ("bathrooms", property_row.bathrooms),
            ("square_feet", property_row.square_feet),
            ("lot_size", property_row.lot_size),
            ("year_built", property_row.year_built),
        ):
            if facts.get(field) is None and value is not None:
                facts[field] = value

    inputs_payload: Dict[str, Any] = {
        key: data.get(key)
        for key in (
            "purchase_price",
            "arv",
            "arv_low",
            "arv_high",
            "rehab",
            "rehab_low",
            "rehab_high",
            "monthly_rent",
            "as_is_value",
            "listing_price",
        )
    }
    inputs_payload["property_facts"] = facts
    inputs_payload["evidence"] = data.get("evidence") or {}
    inputs_payload["risk_flags"] = data.get("risk_flags") or []
    inputs_payload["assumptions"] = assumptions.to_dict()
    inputs_payload["investor_profile"] = profile.to_dict()
    return DealInputs.from_dict(inputs_payload)


def run_analysis(
    inputs: DealInputs,
    include_ai: bool = False,
    settings: Optional[Settings] = None,
) -> Tuple[StrategyComparison, DealScore, Optional[Dict[str, Any]]]:
    """Run the engines. The AI step is optional and never load-bearing."""
    comparison = analyze_all_strategies(inputs)
    scoring = score_deal(inputs, comparison)

    ai_output: Optional[Dict[str, Any]] = None
    if include_ai:
        provider = get_ai_provider(
            settings.atlas_ai_provider if settings else "null",
            **_ai_kwargs(settings),
        )
        try:
            ai_output = run_all_agents(inputs, comparison, provider, scoring.to_dict())
        except Exception:
            # An AI failure must never fail an analysis. The numbers are the
            # product; the narration is a convenience.
            logger.exception("AI agents failed; returning analysis without narration")
            ai_output = None

    return comparison, scoring, ai_output


def _ai_kwargs(settings: Optional[Settings]) -> Dict[str, Any]:
    if settings is None:
        return {}
    provider = (settings.atlas_ai_provider or "null").lower()
    if provider == "anthropic":
        return {
            "api_key": settings.anthropic_api_key,
            "model": settings.atlas_ai_model,
            "timeout_seconds": settings.ai_request_timeout_seconds,
        }
    if provider == "openai":
        return {
            "api_key": settings.openai_api_key,
            "model": settings.atlas_ai_model,
            "timeout_seconds": settings.ai_request_timeout_seconds,
        }
    return {}


def build_response_payload(
    inputs: DealInputs,
    comparison: StrategyComparison,
    scoring: DealScore,
    ai_output: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    comparison_dict = comparison.to_dict()
    return {
        "inputs": inputs.to_dict(),
        "strategies": comparison_dict["strategies"],
        "ranking": comparison_dict["ranking"],
        "recommended_strategy": comparison_dict["recommended_strategy"],
        "alternative_strategy": comparison_dict["alternative_strategy"],
        "rationale": comparison_dict["rationale"],
        "viable_exit_count": comparison_dict["viable_exit_count"],
        "overall_confidence": comparison_dict["overall_confidence"],
        "missing_information": comparison_dict["missing_information"],
        "scoring": scoring.to_dict(),
        "capital_efficiency": comparison_dict["capital_efficiency"],
        "ai_analysis": ai_output,
        "engine_version": engine_version,
    }


def _dec(value: Optional[str]) -> Optional[Decimal]:
    return Decimal(value) if value not in (None, "") else None


def apply_to_model(
    analysis: DealAnalysis,
    inputs: DealInputs,
    comparison: StrategyComparison,
    scoring: DealScore,
    ai_output: Optional[Dict[str, Any]],
) -> DealAnalysis:
    """Flatten an analysis onto its row.

    The denormalised columns exist so the dashboard can sort and filter without
    parsing JSON. The JSON columns exist so nothing is lost.
    """
    a = inputs.assumptions
    recommended = comparison.recommended
    headline = comparison.results.get(recommended) if recommended else None

    analysis.purchase_price = inputs.purchase_price
    analysis.arv_low = inputs.arv_low if inputs.arv_low is not None else inputs.effective_arv
    analysis.arv_high = inputs.arv_high if inputs.arv_high is not None else inputs.effective_arv
    analysis.rehab_low = (
        inputs.rehab_low if inputs.rehab_low is not None else inputs.effective_rehab
    )
    analysis.rehab_high = (
        inputs.rehab_high if inputs.rehab_high is not None else inputs.effective_rehab
    )
    analysis.rent = inputs.monthly_rent

    analysis.vacancy = a.rental.vacancy_percent
    analysis.management = a.rental.management_percent
    analysis.maintenance = a.rental.maintenance_percent
    analysis.capex = a.rental.capex_percent
    analysis.taxes = a.rental.annual_taxes
    analysis.insurance = a.rental.annual_insurance
    analysis.hoa = a.rental.monthly_hoa

    flip = comparison.results.get(Strategy.FLIP)
    if flip is not None and flip.viable:
        costs = flip.detail.get("costs", {})
        analysis.closing_costs = _dec(costs.get("acquisition_closing_costs"))
        analysis.holding_costs = _dec(costs.get("holding_costs"))
        analysis.financing_costs = _dec(costs.get("financing_costs"))
        analysis.selling_costs = _dec(costs.get("selling_costs"))
        analysis.miscellaneous_costs = _dec(costs.get("miscellaneous_costs"))
        analysis.total_basis = _dec(costs.get("total_basis"))

    if headline is not None:
        analysis.profit = headline.profit
        analysis.cash_required = headline.cash_required
        analysis.equity_created = headline.equity_created
        analysis.monthly_cash_flow = headline.monthly_cash_flow
        analysis.annual_cash_flow = headline.annual_cash_flow
        arv_conf = (headline.detail or {}).get("arv_confidence") or {}
        rehab_conf = (headline.detail or {}).get("rehab_confidence") or {}
        analysis.arv_confidence = arv_conf.get("level")
        analysis.rehab_confidence = rehab_conf.get("level")

    analysis.recommended_strategy = recommended.value if recommended else None
    analysis.confidence = comparison.overall_confidence.value
    analysis.deal_score = scoring.score
    analysis.risk_score = scoring.risk_score
    analysis.verdict = scoring.verdict.value
    analysis.requires_human_review = scoring.requires_human_review

    payload = build_response_payload(inputs, comparison, scoring, ai_output)
    analysis.inputs_json = payload["inputs"]
    analysis.assumptions_json = a.to_dict()
    analysis.results_json = {
        "strategies": payload["strategies"],
        "ranking": payload["ranking"],
        "recommended_strategy": payload["recommended_strategy"],
        "alternative_strategy": payload["alternative_strategy"],
        "rationale": payload["rationale"],
        "viable_exit_count": payload["viable_exit_count"],
        "overall_confidence": payload["overall_confidence"],
        "missing_information": payload["missing_information"],
        "capital_efficiency": payload["capital_efficiency"],
    }
    analysis.scoring_json = payload["scoring"]
    if ai_output is not None:
        analysis.ai_analysis_json = ai_output
    analysis.engine_version = engine_version
    # a.schema_version, not the module constant: whatever generation these
    # assumptions were actually built under is what the blob means.
    analysis.assumptions_schema_version = a.schema_version
    return analysis


def stored_analysis_payload(analysis: DealAnalysis) -> Dict[str, Any]:
    """Rebuild the API response from a saved row, without recomputing."""
    results = analysis.results_json or {}
    return {
        "id": analysis.id,
        "property_id": analysis.property_id,
        "name": analysis.name,
        "inputs": analysis.inputs_json or {},
        "strategies": results.get("strategies", {}),
        "ranking": results.get("ranking", []),
        "recommended_strategy": results.get("recommended_strategy"),
        "alternative_strategy": results.get("alternative_strategy"),
        "rationale": results.get("rationale", []),
        "viable_exit_count": results.get("viable_exit_count", 0),
        "overall_confidence": results.get("overall_confidence", "LOW"),
        "missing_information": results.get("missing_information", []),
        "capital_efficiency": results.get("capital_efficiency", {}),
        "scoring": analysis.scoring_json or {},
        "ai_analysis": analysis.ai_analysis_json,
        "engine_version": analysis.engine_version or engine_version,
        "created_at": analysis.created_at,
        "updated_at": analysis.updated_at,
    }
