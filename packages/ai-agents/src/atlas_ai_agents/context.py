"""Building the context an agent is allowed to see.

Two rules are enforced here rather than left to each agent:

**Minimise what leaves the building.** Owner names, mailing addresses, contact
details and the exact street address are stripped before anything is sent to a
model. A model needs the market, the vintage and the numbers to reason about a
deal; it does not need to know who owns the house. Nothing in this payload
identifies a private individual.

**The model receives computed numbers, never raw inputs to compute from.**
Every figure in the context has already been produced by the deterministic
engine. The agent's job is to interpret arithmetic, not to perform it.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from atlas_financial_engine.inputs import DealInputs
from atlas_financial_engine.strategy_engine import StrategyComparison


def _s(value: Optional[Decimal]) -> Optional[str]:
    return str(value) if value is not None else None


def redact_location(inputs: DealInputs) -> Dict[str, Any]:
    """Location at market granularity, never at doorstep granularity."""
    facts = inputs.property_facts
    return {
        "city": facts.city,
        "state": facts.state,
        "zip_code": facts.zip_code,
        "county": facts.county,
    }


def build_context(
    inputs: DealInputs,
    comparison: StrategyComparison,
    scoring: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """The sanitised, computed view of a deal that an agent may reason about."""
    facts = inputs.property_facts
    strategies: Dict[str, Any] = {}
    for strategy, result in comparison.results.items():
        if not result.viable:
            strategies[strategy.value] = {
                "viable": False,
                "reason": result.not_viable_reason,
                "missing_inputs": result.missing_inputs,
            }
            continue
        strategies[strategy.value] = {
            "viable": True,
            "profit": _s(result.profit),
            "cash_required": _s(result.cash_required),
            "roi": _s(result.roi),
            "monthly_cash_flow": _s(result.monthly_cash_flow),
            "equity_created": _s(result.equity_created),
            "dscr": _s(result.dscr),
            "max_purchase_price": _s(result.max_purchase_price),
            "time_to_liquidity_months": result.time_to_liquidity_months,
            "meets_criteria": result.meets_criteria,
            "unmet_criteria": [c.label for c in result.criteria if not c.met],
            "confidence": result.confidence.value,
            "warnings": list(result.warnings),
        }

    return {
        "property": {
            # Deliberately excludes street address and every owner field.
            "location": redact_location(inputs),
            "property_type": facts.property_type,
            "bedrooms": _s(facts.bedrooms),
            "bathrooms": _s(facts.bathrooms),
            "square_feet": _s(facts.square_feet),
            "year_built": facts.year_built,
        },
        "inputs": {
            "purchase_price": _s(inputs.purchase_price),
            "arv": _s(inputs.effective_arv),
            "arv_low": _s(inputs.arv_low),
            "arv_high": _s(inputs.arv_high),
            "rehab": _s(inputs.effective_rehab),
            "rehab_low": _s(inputs.rehab_low),
            "rehab_high": _s(inputs.rehab_high),
            "monthly_rent": _s(inputs.monthly_rent),
        },
        "evidence": inputs.evidence.to_dict(),
        "strategies": strategies,
        "ranking": [
            {"strategy": s.strategy.value, "score": str(s.score)} for s in comparison.scores
        ],
        "recommended_strategy": (
            comparison.recommended.value if comparison.recommended else None
        ),
        "alternative_strategy": (
            comparison.alternative.value if comparison.alternative else None
        ),
        "engine_rationale": list(comparison.rationale),
        "overall_confidence": comparison.overall_confidence.value,
        "viable_exit_count": comparison.viable_exit_count,
        "missing_information": list(comparison.missing_information),
        "scoring": _redact_scoring(scoring),
    }


def _redact_scoring(scoring: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not scoring:
        return None
    return {
        "score": scoring.get("score"),
        "verdict": scoring.get("verdict"),
        "coverage": scoring.get("coverage"),
        "risk_score": scoring.get("risk_score"),
        "requires_human_review": scoring.get("requires_human_review"),
        "risk_flags": [
            {
                "code": f.get("code"),
                "label": f.get("label"),
                "severity": f.get("severity"),
            }
            for f in scoring.get("risk_flags", [])
        ],
    }


MISSING_FIELD_LABELS = {
    "purchase_price": "Purchase price or target offer",
    "arv": "After-repair value supported by comparable sales",
    "rehab": "Rehab estimate from a scope of work or contractor bid",
    "monthly_rent": "Market rent estimate",
    # Expenses are reported with the section they belong to, because the
    # holding-period figure and the rental-period figure are edited separately
    # and can legitimately differ (a vacant rehab is not insured as a rental).
    "holding.annual_taxes": "Annual property tax bill (holding period)",
    "holding.annual_insurance": "Annual insurance premium (holding period)",
    "holding.monthly_hoa": "Monthly HOA dues while held (0 if none)",
    "holding.monthly_utilities": "Monthly utilities while held (0 if none)",
    "rental.annual_taxes": "Annual property tax bill",
    "rental.annual_insurance": "Annual insurance premium",
    "rental.monthly_hoa": "Monthly HOA dues (0 if none)",
}


def describe_missing(missing: List[str]) -> List[str]:
    return [MISSING_FIELD_LABELS.get(field, field) for field in missing]
