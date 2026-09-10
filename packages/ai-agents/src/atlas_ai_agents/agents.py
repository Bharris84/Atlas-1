"""The Atlas agents.

Three agents, one hard rule between them:

    The agents receive completed calculations. They never produce a number.

Every figure in an agent's output is copied from the deterministic engine.
What the model contributes is prose, challenges and questions — clearly
separated from the numbers and labelled ``INFERENCE``, so a reader always knows
which parts were computed and which were reasoned.

Each agent composes a complete, useful result deterministically first. A model,
when configured, adds narrative on top. If the model is absent, slow, or
returns something unparseable, the deterministic result stands on its own.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from atlas_financial_engine import Assertion, Confidence, Strategy
from atlas_financial_engine.inputs import DealInputs
from atlas_financial_engine.strategy_engine import STRATEGY_LABELS, StrategyComparison

from .context import build_context, describe_missing
from .providers import (
    AIProvider,
    AIProviderError,
    NullProvider,
    as_string_list,
    extract_json,
)

logger = logging.getLogger("atlas.ai.agents")


@dataclass(frozen=True)
class Claim:
    """One labelled statement. The label is the point."""

    label: str
    value: Optional[str]
    assertion: Assertion
    source: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "value": self.value,
            "assertion": self.assertion.value,
            "source": self.source,
        }


@dataclass(frozen=True)
class AgentOutput:
    agent: str
    provider: str
    model: Optional[str]
    generated_at: str
    deterministic: bool
    summary: str
    claims: List[Claim] = field(default_factory=list)
    narrative: List[str] = field(default_factory=list)
    challenges: List[str] = field(default_factory=list)
    questions: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    missing_information: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent,
            "provider": self.provider,
            "model": self.model,
            "generated_at": self.generated_at,
            "deterministic": self.deterministic,
            "summary": self.summary,
            "claims": [c.to_dict() for c in self.claims],
            "narrative": list(self.narrative),
            "challenges": list(self.challenges),
            "questions": list(self.questions),
            "risks": list(self.risks),
            "missing_information": list(self.missing_information),
            "sources": list(self.sources),
            "disclaimer": (
                "Narrative, challenges and questions are AI-generated interpretation "
                "(INFERENCE). Every figure shown is computed by the Atlas financial "
                "engine, not by a language model."
            ),
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _money(value: Optional[str]) -> str:
    if value is None:
        return "unknown"
    try:
        return f"${Decimal(value):,.0f}"
    except Exception:
        return str(value)


def _percent(value: Optional[str]) -> str:
    if value is None:
        return "unknown"
    try:
        return f"{Decimal(value) * 100:.1f}%"
    except Exception:
        return str(value)


BASE_SYSTEM_PROMPT = """You are an analyst inside Atlas, a real-estate underwriting platform.

Absolute rules:
1. You must NOT perform arithmetic or state any figure that is not already
   present in the data provided to you. Every number has been computed by a
   deterministic engine. If a number you want is not given, say it is unknown.
2. Distinguish FACT, ESTIMATE, INFERENCE and UNKNOWN. Never present an
   estimate as a verified fact.
3. Never invent comparable sales, market conditions, ownership details or
   local knowledge. If you do not have it, say so.
4. Be an analyst, not a salesperson. Say plainly when a deal is weak.

Respond with a single JSON object and no other text."""


def _call_model(
    provider: AIProvider, system: str, prompt: str, max_tokens: int = 1400
) -> Optional[Dict[str, Any]]:
    """Call the model, returning ``None`` on any failure.

    Returning None rather than raising is deliberate: a failed narration must
    degrade to the deterministic output, never break an analysis.
    """
    if isinstance(provider, NullProvider):
        return None
    try:
        completion = provider.complete(system=system, prompt=prompt, max_tokens=max_tokens)
    except AIProviderError as exc:
        logger.warning("AI provider failed, falling back to deterministic output: %s", exc)
        return None
    parsed = extract_json(completion.text)
    if parsed is None:
        logger.warning("AI provider returned unparseable output; using deterministic output")
        return None
    parsed["_provider"] = completion.provider
    parsed["_model"] = completion.model
    return parsed


# ---------------------------------------------------------------------------
# Research agent
# ---------------------------------------------------------------------------


def _research_claims(inputs: DealInputs, context: Dict[str, Any]) -> List[Claim]:
    """What is known about this property, each item labelled."""
    from atlas_financial_engine.confidence import assess_arv, assess_rehab, assess_rent

    facts = inputs.property_facts
    claims: List[Claim] = []

    def add(label: str, value: Optional[Any], assertion: Assertion, source: str) -> None:
        claims.append(
            Claim(
                label=label,
                value=str(value) if value is not None else None,
                assertion=assertion if value is not None else Assertion.UNKNOWN,
                source=source,
            )
        )

    add("Property type", facts.property_type, Assertion.FACT, "user-entered record")
    add("Bedrooms", facts.bedrooms, Assertion.FACT, "user-entered record")
    add("Bathrooms", facts.bathrooms, Assertion.FACT, "user-entered record")
    add("Square feet", facts.square_feet, Assertion.FACT, "user-entered record")
    add("Year built", facts.year_built, Assertion.FACT, "user-entered record")
    add(
        "Market",
        ", ".join(p for p in [facts.city, facts.state] if p) or None,
        Assertion.FACT,
        "user-entered record",
    )

    arv_conf = assess_arv(inputs.evidence, inputs.arv_low, inputs.arv_high)
    claims.append(
        Claim(
            label="After-repair value",
            value=str(inputs.effective_arv) if inputs.effective_arv is not None else None,
            assertion=arv_conf.assertion,
            source=f"{inputs.evidence.arv_basis.value} ({arv_conf.level.value} confidence)",
        )
    )
    rehab_conf = assess_rehab(inputs.evidence, inputs.rehab_low, inputs.rehab_high)
    claims.append(
        Claim(
            label="Rehab estimate",
            value=str(inputs.effective_rehab) if inputs.effective_rehab is not None else None,
            assertion=rehab_conf.assertion,
            source=f"{inputs.evidence.rehab_basis.value} ({rehab_conf.level.value} confidence)",
        )
    )
    rent_conf = assess_rent(inputs.evidence)
    claims.append(
        Claim(
            label="Monthly rent",
            value=str(inputs.monthly_rent) if inputs.monthly_rent is not None else None,
            assertion=rent_conf.assertion,
            source=f"{inputs.evidence.rent_basis.value} ({rent_conf.level.value} confidence)",
        )
    )
    claims.append(
        Claim(
            label="Purchase price",
            value=str(inputs.purchase_price) if inputs.purchase_price is not None else None,
            assertion=Assertion.FACT if inputs.purchase_price is not None else Assertion.UNKNOWN,
            source="user-entered offer or contract price",
        )
    )
    return claims


def _research_deterministic(
    inputs: DealInputs, comparison: StrategyComparison, context: Dict[str, Any]
) -> Dict[str, List[str]]:
    evidence = inputs.evidence
    narrative: List[str] = []
    questions: List[str] = []
    risks: List[str] = []

    location = ", ".join(
        p for p in [inputs.property_facts.city, inputs.property_facts.state] if p
    )
    narrative.append(
        f"Atlas holds {sum(1 for c in _research_claims(inputs, context) if c.value)} of "
        f"{len(_research_claims(inputs, context))} core data points for this property"
        + (f" in {location}." if location else ".")
    )

    if evidence.comp_count:
        narrative.append(
            f"The value rests on {evidence.comp_count} comparable sale(s)"
            + (
                f", averaging {evidence.average_comp_age_days} days old"
                if evidence.average_comp_age_days is not None
                else ""
            )
            + "."
        )
    else:
        narrative.append("No comparable sales are recorded against this property.")
        questions.append(
            "Pull at least three recent closed sales within a mile with similar beds, "
            "baths and square footage."
        )

    if not evidence.property_visited:
        questions.append("Walk the property, or get someone trusted to walk it.")
    if not evidence.title_reviewed:
        questions.append("Order a title search before committing to a contract price.")
    # `is None` and not `== 0`: an explicit zero is an answer, and asking the
    # user to re-establish a figure they already entered is how a checklist
    # trains people to stop reading it.
    unknown_expenses = inputs.assumptions.rental.unknown_fields()
    if "annual_taxes" in unknown_expenses:
        questions.append("Pull the actual property tax bill from the county record.")
    if "annual_insurance" in unknown_expenses:
        questions.append("Get an insurance quote; premiums vary widely by state and age.")
    if "monthly_hoa" in unknown_expenses:
        questions.append(
            "Confirm whether the property is in an HOA, and record 0 if it is not."
        )

    for result in comparison.results.values():
        risks.extend(result.warnings)

    return {"narrative": narrative, "questions": questions, "risks": sorted(set(risks))}


def research_property(
    inputs: DealInputs,
    comparison: StrategyComparison,
    provider: Optional[AIProvider] = None,
    scoring: Optional[Dict[str, Any]] = None,
) -> AgentOutput:
    """Summarise what is known, what is estimated, and what is missing."""
    provider = provider or NullProvider()
    context = build_context(inputs, comparison, scoring)
    claims = _research_claims(inputs, context)
    base = _research_deterministic(inputs, comparison, context)
    missing = describe_missing(comparison.missing_information)

    known = sum(1 for c in claims if c.value is not None)
    summary = (
        f"{known} of {len(claims)} core data points recorded. "
        f"Overall confidence: {comparison.overall_confidence.value}."
    )

    prompt = (
        "Summarise the research picture for this property.\n\n"
        "Return JSON with keys: summary (string), narrative (array of strings), "
        "questions (array of strings), risks (array of strings).\n"
        "Do not state any figure that is not in the data below.\n\n"
        f"{context}"
    )
    parsed = _call_model(provider, BASE_SYSTEM_PROMPT, prompt)

    if parsed:
        return AgentOutput(
            agent="research",
            provider=parsed.get("_provider", provider.name),
            model=parsed.get("_model"),
            generated_at=_now(),
            deterministic=False,
            summary=str(parsed.get("summary") or summary)[:600],
            claims=claims,
            narrative=as_string_list(parsed.get("narrative")) or base["narrative"],
            questions=as_string_list(parsed.get("questions")) or base["questions"],
            risks=as_string_list(parsed.get("risks")) or base["risks"],
            missing_information=missing,
            sources=_sources(inputs),
        )

    return AgentOutput(
        agent="research",
        provider="null",
        model=None,
        generated_at=_now(),
        deterministic=True,
        summary=summary,
        claims=claims,
        narrative=base["narrative"],
        questions=base["questions"],
        risks=base["risks"],
        missing_information=missing,
        sources=_sources(inputs),
    )


def _sources(inputs: DealInputs) -> List[str]:
    """Cite what the analysis actually rests on."""
    sources = [
        f"ARV basis: {inputs.evidence.arv_basis.value}",
        f"Rehab basis: {inputs.evidence.rehab_basis.value}",
        f"Rent basis: {inputs.evidence.rent_basis.value}",
    ]
    if inputs.evidence.comp_count:
        sources.append(f"{inputs.evidence.comp_count} comparable sale(s) on file")
    return sources


# ---------------------------------------------------------------------------
# Underwriting agent
# ---------------------------------------------------------------------------


UNDERWRITING_SYSTEM_PROMPT = (
    BASE_SYSTEM_PROMPT
    + """

You are the underwriting reviewer. You did not build this model and you are not
here to agree with it. Explain what the computed results mean, challenge the
assumptions that drive them, and name the diligence that would change your mind.
Pay particular attention to any figure whose supporting evidence is weak."""
)


def _underwriting_challenges(
    inputs: DealInputs, comparison: StrategyComparison
) -> List[str]:
    """Deterministic challenges to the assumptions driving the result."""
    challenges: List[str] = []
    evidence = inputs.evidence
    arv = inputs.effective_arv
    rehab = inputs.effective_rehab

    if arv is not None and evidence.arv_basis.value in (
        "unknown",
        "user_entered",
        "automated_valuation",
        "list_price",
    ):
        challenges.append(
            f"The entire model is anchored to an ARV of {_money(str(arv))}, which is "
            f"supported only by '{evidence.arv_basis.value}'. Every profit figure moves "
            "one-for-one with this number."
        )

    if inputs.arv_low is not None and inputs.arv_high is not None and arv is not None:
        spread = Decimal(inputs.arv_high) - Decimal(inputs.arv_low)
        challenges.append(
            f"The ARV range spans {_money(str(spread))}. At the low end, every profit "
            "figure in this analysis falls by roughly that amount less selling costs."
        )

    if rehab is not None and evidence.rehab_basis.value in (
        "unknown",
        "user_entered",
        "per_sqft_estimate",
    ):
        challenges.append(
            f"The rehab of {_money(str(rehab))} is not backed by a scope or a bid. "
            "Rehab overruns are the most common cause of a flip missing its target."
        )

    if not evidence.property_visited:
        challenges.append(
            "Nobody has walked the property. Condition risk is entirely unpriced."
        )

    unknown_expenses = inputs.assumptions.rental.unknown_fields()
    if "annual_taxes" in unknown_expenses:
        challenges.append(
            "Property taxes are not established, so they are absent from these "
            "figures. That overstates NOI and every rental return derived from it."
        )
    if "annual_insurance" in unknown_expenses:
        challenges.append(
            "Insurance is not established and is therefore missing from these "
            "figures. In coastal and older-home markets that is a material omission."
        )

    flip = comparison.results.get(Strategy.FLIP)
    if flip is not None and flip.viable and flip.profit is not None and arv:
        margin = Decimal(flip.profit) / Decimal(arv)
        if margin < Decimal("0.12"):
            challenges.append(
                f"Flip margin is {margin * 100:.1f}% of ARV. A single-digit percentage "
                "miss on the resale price erases the profit."
            )

    if comparison.viable_exit_count <= 1:
        challenges.append(
            "There is at most one exit that clears the buy box. If it stops working, "
            "there is no fallback plan for this property."
        )
    return challenges


def underwrite(
    inputs: DealInputs,
    comparison: StrategyComparison,
    provider: Optional[AIProvider] = None,
    scoring: Optional[Dict[str, Any]] = None,
) -> AgentOutput:
    """Explain and challenge the computed results. Never recompute them."""
    provider = provider or NullProvider()
    context = build_context(inputs, comparison, scoring)
    challenges = _underwriting_challenges(inputs, comparison)
    missing = describe_missing(comparison.missing_information)

    narrative: List[str] = list(comparison.rationale)
    recommended = comparison.recommended
    if recommended is not None:
        result = comparison.results[recommended]
        narrative.append(
            f"On the numbers as entered, {STRATEGY_LABELS[recommended]} produces "
            f"{_money(str(result.profit) if result.profit is not None else None)} "
            f"against {_money(str(result.cash_required) if result.cash_required is not None else None)} "
            "of committed capital."
        )
        if result.max_purchase_price is not None and inputs.purchase_price is not None:
            delta = Decimal(result.max_purchase_price) - Decimal(inputs.purchase_price)
            if delta < 0:
                narrative.append(
                    f"The price is {_money(str(abs(delta)))} above the maximum this "
                    "strategy supports at the stated targets."
                )
            else:
                narrative.append(
                    f"There is {_money(str(delta))} of room between the price and the "
                    "maximum this strategy supports."
                )

    summary = (
        f"Reviewed {sum(1 for r in comparison.results.values() if r.viable)} viable "
        f"strategies. {len(challenges)} assumption(s) warrant challenge."
    )

    prompt = (
        "Review this underwriting. Explain what the computed results mean, challenge "
        "the assumptions driving them, and list the diligence you would require.\n\n"
        "Return JSON with keys: summary (string), narrative (array), challenges "
        "(array), questions (array).\n"
        "Every number you mention must already appear below. Do not calculate.\n\n"
        f"{context}"
    )
    parsed = _call_model(provider, UNDERWRITING_SYSTEM_PROMPT, prompt)

    if parsed:
        return AgentOutput(
            agent="underwriting",
            provider=parsed.get("_provider", provider.name),
            model=parsed.get("_model"),
            generated_at=_now(),
            deterministic=False,
            summary=str(parsed.get("summary") or summary)[:600],
            narrative=as_string_list(parsed.get("narrative")) or narrative,
            challenges=as_string_list(parsed.get("challenges")) or challenges,
            questions=as_string_list(parsed.get("questions")),
            missing_information=missing,
            sources=_sources(inputs),
        )

    return AgentOutput(
        agent="underwriting",
        provider="null",
        model=None,
        generated_at=_now(),
        deterministic=True,
        summary=summary,
        narrative=narrative,
        challenges=challenges,
        questions=[
            "Which single assumption, if wrong by 10%, would change the decision?",
        ],
        missing_information=missing,
        sources=_sources(inputs),
    )


# ---------------------------------------------------------------------------
# Strategist
# ---------------------------------------------------------------------------


STRATEGIST_SYSTEM_PROMPT = (
    BASE_SYSTEM_PROMPT
    + """

You are the strategist. Compare the strategies that were computed and explain
why the recommended one fits this property better than the alternatives. State
what would have to be true for the alternative to become the better choice.
Capital efficiency matters more than headline profit for an early-stage
operator."""
)


def strategise(
    inputs: DealInputs,
    comparison: StrategyComparison,
    provider: Optional[AIProvider] = None,
    scoring: Optional[Dict[str, Any]] = None,
) -> AgentOutput:
    """Compare strategies and explain the recommendation."""
    provider = provider or NullProvider()
    context = build_context(inputs, comparison, scoring)

    recommended = comparison.recommended
    alternative = comparison.alternative
    narrative = list(comparison.rationale)
    risks: List[str] = []
    questions: List[str] = []

    if recommended is not None:
        result = comparison.results[recommended]
        risks.extend(result.warnings)
        if result.confidence != Confidence.HIGH:
            questions.append(
                f"Confidence in the recommended strategy is {result.confidence.value}. "
                "Strengthen the ARV or rehab evidence before acting on it."
            )
    if alternative is not None:
        alt = comparison.results[alternative]
        unmet = [c.label for c in alt.criteria if not c.met]
        if unmet:
            narrative.append(
                f"{STRATEGY_LABELS[alternative]} would become viable if it cleared: "
                + ", ".join(unmet)
                + "."
            )

    summary = (
        f"Recommended: {STRATEGY_LABELS[recommended]}."
        if recommended is not None
        else "No strategy is recommendable on the information available."
    )

    prompt = (
        "Compare these strategies and justify the recommendation. Say what would have "
        "to change for the alternative to win.\n\n"
        "Return JSON with keys: summary (string), narrative (array), risks (array), "
        "questions (array).\n"
        "Use only the computed figures below.\n\n"
        f"{context}"
    )
    parsed = _call_model(provider, STRATEGIST_SYSTEM_PROMPT, prompt)

    if parsed:
        return AgentOutput(
            agent="strategist",
            provider=parsed.get("_provider", provider.name),
            model=parsed.get("_model"),
            generated_at=_now(),
            deterministic=False,
            summary=str(parsed.get("summary") or summary)[:600],
            narrative=as_string_list(parsed.get("narrative")) or narrative,
            risks=as_string_list(parsed.get("risks")) or sorted(set(risks)),
            questions=as_string_list(parsed.get("questions")) or questions,
            missing_information=describe_missing(comparison.missing_information),
            sources=_sources(inputs),
        )

    return AgentOutput(
        agent="strategist",
        provider="null",
        model=None,
        generated_at=_now(),
        deterministic=True,
        summary=summary,
        narrative=narrative,
        risks=sorted(set(risks)),
        questions=questions,
        missing_information=describe_missing(comparison.missing_information),
        sources=_sources(inputs),
    )


def run_all_agents(
    inputs: DealInputs,
    comparison: StrategyComparison,
    provider: Optional[AIProvider] = None,
    scoring: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run every agent and return their combined output."""
    provider = provider or NullProvider()
    return {
        "research": research_property(inputs, comparison, provider, scoring).to_dict(),
        "underwriting": underwrite(inputs, comparison, provider, scoring).to_dict(),
        "strategist": strategise(inputs, comparison, provider, scoring).to_dict(),
    }
