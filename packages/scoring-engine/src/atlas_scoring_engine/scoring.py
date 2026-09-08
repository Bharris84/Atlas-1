"""Deal scoring.

The score is a weighted average over seven categories. The important design
decision is how Atlas handles categories it cannot assess yet: seller situation
and market data are not available in V0.1.

Scoring an unknown as zero would make every deal look bad. Scoring it as
average would invent information. Atlas does neither: an unassessable category
is EXCLUDED and the remaining weights are renormalised, with the proportion of
the rubric actually covered reported as ``coverage``. A deal scored on 60% of
the rubric is not allowed to reach PURSUE on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from atlas_financial_engine import Confidence, RiskSeverity, Strategy, Verdict
from atlas_financial_engine.inputs import DealInputs
from atlas_financial_engine.money import D, ZERO, ratio, safe_div
from atlas_financial_engine.strategy_engine import StrategyComparison

from .risk import RiskFlag, all_risk_flags

PURSUE_THRESHOLD = D("80")
INVESTIGATE_THRESHOLD = D("60")
# Below this share of the rubric, a score cannot support a PURSUE decision.
#
# In V0.1 seller situation (15%) and market (15%) are never assessable, so the
# ceiling is 70%. This threshold therefore means: a deal cannot be marked
# PURSUE unless, at minimum, the physical property attributes have been
# recorded. Atlas will not tell someone to chase a house it knows nothing
# about. The threshold falls back to its plain meaning once the CRM and market
# phases make those categories assessable.
MINIMUM_COVERAGE_FOR_PURSUE = D("0.65")


@dataclass(frozen=True)
class ScoringWeights:
    financial_potential: Decimal = D("0.25")
    equity: Decimal = D("0.20")
    seller_situation: Decimal = D("0.15")
    market: Decimal = D("0.15")
    property_quality: Decimal = D("0.10")
    exit_options: Decimal = D("0.10")
    risk: Decimal = D("0.05")

    def as_dict(self) -> Dict[str, Decimal]:
        return {
            "financial_potential": self.financial_potential,
            "equity": self.equity,
            "seller_situation": self.seller_situation,
            "market": self.market,
            "property_quality": self.property_quality,
            "exit_options": self.exit_options,
            "risk": self.risk,
        }


@dataclass(frozen=True)
class ScoreComponent:
    name: str
    label: str
    weight: Decimal
    score: Optional[Decimal]
    assessed: bool
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "weight": str(self.weight),
            "score": str(self.score) if self.score is not None else None,
            "assessed": self.assessed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class DealScore:
    score: Optional[Decimal]
    verdict: Verdict
    verdict_reason: str
    coverage: Decimal
    components: List[ScoreComponent]
    risk_flags: List[RiskFlag]
    risk_score: Decimal
    requires_human_review: bool
    confidence: Confidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": str(self.score) if self.score is not None else None,
            "verdict": self.verdict.value,
            "verdict_reason": self.verdict_reason,
            "coverage": str(self.coverage),
            "components": [c.to_dict() for c in self.components],
            "risk_flags": [f.to_dict() for f in self.risk_flags],
            "risk_score": str(self.risk_score),
            "requires_human_review": self.requires_human_review,
            "confidence": self.confidence.value,
        }


def _unassessed(name: str, label: str, weight: Decimal, reason: str) -> ScoreComponent:
    return ScoreComponent(
        name=name, label=label, weight=weight, score=None, assessed=False, reason=reason
    )


def _score_financial_potential(
    comparison: StrategyComparison, weight: Decimal
) -> ScoreComponent:
    if not comparison.scores:
        return _unassessed(
            "financial_potential",
            "Financial potential",
            weight,
            "No strategy could be evaluated.",
        )
    best = comparison.scores[0]
    return ScoreComponent(
        name="financial_potential",
        label="Financial potential",
        weight=weight,
        score=best.score,
        assessed=True,
        reason=(
            f"Best strategy is {best.strategy.value.replace('_', ' ')}, "
            f"scoring {best.score:.0f} on profit, capital efficiency and return."
        ),
    )


def _score_equity(
    inputs: DealInputs, comparison: StrategyComparison, weight: Decimal
) -> ScoreComponent:
    arv = inputs.effective_arv
    if arv is None or arv <= 0:
        return _unassessed(
            "equity", "Equity position", weight, "No after-repair value available."
        )
    best_equity = max(
        (r.equity_created for r in comparison.results.values() if r.equity_created is not None),
        default=None,
    )
    if best_equity is None:
        return _unassessed(
            "equity", "Equity position", weight, "No strategy produced an equity figure."
        )
    equity_ratio = safe_div(best_equity, arv)
    if equity_ratio is None:
        return _unassessed("equity", "Equity position", weight, "Equity is undefined.")
    # 30% equity to ARV is treated as a full score.
    score = min(max(equity_ratio / D("0.30") * D("100"), ZERO), D("100"))
    return ScoreComponent(
        name="equity",
        label="Equity position",
        weight=weight,
        score=ratio(score),
        assessed=True,
        reason=(
            f"Best strategy creates {equity_ratio * 100:.1f}% equity against ARV "
            f"(${best_equity:,.0f})."
        ),
    )


def _score_property(inputs: DealInputs, weight: Decimal) -> ScoreComponent:
    """Scored on how much is actually known about the physical asset.

    This is a data-completeness score, not a judgement about whether the house
    is nice. Atlas has no basis for the latter in V0.1.
    """
    facts = inputs.property_facts
    known = [
        facts.property_type is not None,
        facts.bedrooms is not None,
        facts.bathrooms is not None,
        facts.square_feet is not None,
        facts.year_built is not None,
    ]
    if not any(known):
        return _unassessed(
            "property_quality",
            "Property profile",
            weight,
            "No physical property details recorded.",
        )
    score = D(sum(1 for k in known if k)) / D(len(known)) * D("100")
    return ScoreComponent(
        name="property_quality",
        label="Property profile",
        weight=weight,
        score=ratio(score),
        assessed=True,
        reason=(
            f"{sum(1 for k in known if k)} of {len(known)} core property attributes "
            "are recorded. This measures data completeness, not desirability."
        ),
    )


def _score_exit_options(comparison: StrategyComparison, weight: Decimal) -> ScoreComponent:
    count = comparison.viable_exit_count
    # Three or more independent exits is treated as full optionality.
    score = min(D(count) / D("3") * D("100"), D("100"))
    return ScoreComponent(
        name="exit_options",
        label="Exit optionality",
        weight=weight,
        score=ratio(score),
        assessed=True,
        reason=f"{count} of 5 strategies clear their own buy box at this price.",
    )


def compute_risk_score(flags: List[RiskFlag], confidence: Confidence) -> Decimal:
    """0-100, higher is safer."""
    base = {
        Confidence.HIGH: D("90"),
        Confidence.MEDIUM: D("70"),
        Confidence.LOW: D("45"),
    }[confidence]
    for flag in flags:
        if flag.severity == RiskSeverity.CRITICAL:
            base -= D("25")
        elif flag.severity == RiskSeverity.WARNING:
            base -= D("7")
    return ratio(max(min(base, D("100")), ZERO))


def score_deal(
    inputs: DealInputs,
    comparison: StrategyComparison,
    weights: Optional[ScoringWeights] = None,
) -> DealScore:
    w = weights or ScoringWeights()
    flags = all_risk_flags(inputs, comparison)
    risk_score = compute_risk_score(flags, comparison.overall_confidence)

    components: List[ScoreComponent] = [
        _score_financial_potential(comparison, w.financial_potential),
        _score_equity(inputs, comparison, w.equity),
        # Seller and market intelligence arrive in later phases (CRM and market
        # discovery). Until then Atlas declines to guess rather than padding
        # the score with an invented average.
        _unassessed(
            "seller_situation",
            "Seller situation",
            w.seller_situation,
            "No seller or ownership context recorded. Atlas does not infer motivation "
            "from ownership data.",
        ),
        _unassessed(
            "market",
            "Market",
            w.market,
            "No market data connected yet. Requires a data provider or manual entry.",
        ),
        _score_property(inputs, w.property_quality),
        _score_exit_options(comparison, w.exit_options),
        ScoreComponent(
            name="risk",
            label="Risk",
            weight=w.risk,
            score=risk_score,
            assessed=True,
            reason=f"{len(flags)} risk flag(s) recorded.",
        ),
    ]

    assessed = [c for c in components if c.assessed and c.score is not None]
    total_weight = sum((c.weight for c in assessed), ZERO)
    coverage = ratio(total_weight) if total_weight > 0 else ZERO

    score: Optional[Decimal] = None
    if total_weight > 0:
        weighted = sum((c.score * c.weight for c in assessed), ZERO)
        score = ratio(weighted / total_weight)

    blocking = [f for f in flags if f.blocks_pursue]
    verdict, reason = _decide(score, coverage, blocking)

    return DealScore(
        score=score,
        verdict=verdict,
        verdict_reason=reason,
        coverage=coverage,
        components=components,
        risk_flags=flags,
        risk_score=risk_score,
        requires_human_review=bool(blocking),
        confidence=comparison.overall_confidence,
    )


def _decide(
    score: Optional[Decimal], coverage: Decimal, blocking: List[RiskFlag]
) -> tuple[Verdict, str]:
    """Turn a score into a decision, with hard risk flags overriding."""
    if blocking:
        labels = ", ".join(f.label for f in blocking)
        return (
            Verdict.HUMAN_REVIEW_REQUIRED,
            f"Blocking risk flag(s) require a person to review this deal: {labels}. "
            "The numeric score does not override this.",
        )
    if score is None:
        return (
            Verdict.HUMAN_REVIEW_REQUIRED,
            "Not enough information to score this deal.",
        )
    if score >= PURSUE_THRESHOLD:
        if coverage < MINIMUM_COVERAGE_FOR_PURSUE:
            return (
                Verdict.INVESTIGATE,
                f"Scores {score:.0f}, but only {coverage * 100:.0f}% of the scoring "
                "rubric could be assessed. Gather the missing information before "
                "committing.",
            )
        return (Verdict.PURSUE, f"Scores {score:.0f} across {coverage * 100:.0f}% of the rubric.")
    if score >= INVESTIGATE_THRESHOLD:
        return (
            Verdict.INVESTIGATE,
            f"Scores {score:.0f}. Worth more diligence, not yet worth an offer.",
        )
    return (Verdict.PASS, f"Scores {score:.0f}, below the {INVESTIGATE_THRESHOLD} threshold.")
