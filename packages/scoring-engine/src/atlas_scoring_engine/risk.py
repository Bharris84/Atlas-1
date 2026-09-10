"""Risk flags.

A deal score is a summary, and summaries hide things. Risk flags are the
mechanism that stops a high score from papering over a deal-killing unknown:
a CRITICAL flag overrides the score entirely and routes the deal to human
review, no matter how attractive the arithmetic looks.

Flags come from two places:

* DERIVED — computed from the analysis itself (e.g. the ARV rests on an
  automated estimate, so it is not verified).
* DECLARED — raised by a user or, later, by the AI research agent.

Nothing here infers seller motivation. A flag is a classification of a fact,
never a conclusion about what a person wants.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from atlas_financial_engine import Confidence, RehabBasis, RiskSeverity, Strategy, ValueBasis
from atlas_financial_engine.inputs import DealInputs
from atlas_financial_engine.money import D, safe_div
from atlas_financial_engine.strategy_engine import StrategyComparison


@dataclass(frozen=True)
class RiskFlag:
    code: str
    label: str
    severity: RiskSeverity
    detail: str
    # A blocking flag forces human review regardless of the deal score.
    blocks_pursue: bool = False
    source: str = "derived"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "label": self.label,
            "severity": self.severity.value,
            "detail": self.detail,
            "blocks_pursue": self.blocks_pursue,
            "source": self.source,
        }


# Flags a user (or later, the research agent) can declare explicitly. These are
# the hard risks that must stop an automated PURSUE recommendation.
DECLARABLE_FLAGS: Dict[str, RiskFlag] = {
    "title_issue_suspected": RiskFlag(
        code="title_issue_suspected",
        label="Possible title defect",
        severity=RiskSeverity.CRITICAL,
        detail=(
            "A title problem is suspected. Liens, heirs, clouded title and unreleased "
            "mortgages can make a contract unassignable and unclosable."
        ),
        blocks_pursue=True,
        source="declared",
    ),
    "structural_concern": RiskFlag(
        code="structural_concern",
        label="Structural uncertainty",
        severity=RiskSeverity.CRITICAL,
        detail=(
            "Foundation, roof structure or framing condition is uncertain. Structural "
            "scope is the most common cause of a rehab budget doubling."
        ),
        blocks_pursue=True,
        source="declared",
    ),
    "environmental_concern": RiskFlag(
        code="environmental_concern",
        label="Environmental concern",
        severity=RiskSeverity.CRITICAL,
        detail=(
            "Possible septic, well, flood, mould, asbestos, lead, buried tank or "
            "contamination issue. These are specialist scopes with open-ended cost."
        ),
        blocks_pursue=True,
        source="declared",
    ),
    "financing_uncertainty": RiskFlag(
        code="financing_uncertainty",
        label="Severe financing uncertainty",
        severity=RiskSeverity.CRITICAL,
        detail="Funding for this deal is not identified or not committed.",
        blocks_pursue=True,
        source="declared",
    ),
    "occupied_property": RiskFlag(
        code="occupied_property",
        label="Occupied property",
        severity=RiskSeverity.WARNING,
        detail=(
            "The property is occupied. Delivery of vacant possession, tenant rights "
            "and relocation cost all affect timeline and price."
        ),
        source="declared",
    ),
    "permit_or_code_issue": RiskFlag(
        code="permit_or_code_issue",
        label="Permit or code enforcement issue",
        severity=RiskSeverity.WARNING,
        detail="Open permits or code violations may need to be cured before closing.",
        source="declared",
    ),
    "hoa_restrictions": RiskFlag(
        code="hoa_restrictions",
        label="HOA restrictions",
        severity=RiskSeverity.WARNING,
        detail="HOA rules may restrict rentals, assignment or exterior work.",
        source="declared",
    ),
    "flood_zone": RiskFlag(
        code="flood_zone",
        label="Flood zone",
        severity=RiskSeverity.WARNING,
        detail=(
            "Property may sit in a flood zone, which changes insurance cost and "
            "buyer appetite materially."
        ),
        source="declared",
    ),
}

HEAVY_REHAB_RATIO = D("0.30")
OLD_CONSTRUCTION_YEAR = 1960

# Human-readable names for the dotted assumption paths reported by
# Assumptions.blocking_unknown_expenses().
_EXPENSE_LABELS = {
    "holding.annual_taxes": "holding-period property taxes",
    "holding.annual_insurance": "holding-period insurance",
    "rental.annual_taxes": "property taxes",
    "rental.annual_insurance": "insurance",
}


def derive_risk_flags(
    inputs: DealInputs, comparison: StrategyComparison
) -> List[RiskFlag]:
    """Compute the risk flags implied by the analysis itself."""
    flags: List[RiskFlag] = []
    arv = inputs.effective_arv
    rehab = inputs.effective_rehab

    # --- Valuation risk -----------------------------------------------------
    if arv is None:
        flags.append(
            RiskFlag(
                code="arv_unknown",
                label="No after-repair value",
                severity=RiskSeverity.CRITICAL,
                detail="Without an ARV, no exit can be priced.",
                blocks_pursue=True,
            )
        )
    elif inputs.evidence.arv_basis in (
        ValueBasis.UNKNOWN,
        ValueBasis.USER_ENTERED,
        ValueBasis.AUTOMATED_VALUATION,
        ValueBasis.LIST_PRICE,
    ):
        flags.append(
            RiskFlag(
                code="unverified_arv",
                label="Unverified ARV",
                severity=RiskSeverity.CRITICAL,
                detail=(
                    "The after-repair value is not supported by closed comparable "
                    "sales or an appraisal. Every strategy's profit is derived from "
                    "this number."
                ),
                blocks_pursue=True,
            )
        )

    # --- Rehab risk ---------------------------------------------------------
    if rehab is not None and arv is not None and arv > 0:
        rehab_ratio = safe_div(rehab, arv)
        heavy = rehab_ratio is not None and rehab_ratio > HEAVY_REHAB_RATIO
        weak_basis = inputs.evidence.rehab_basis in (
            RehabBasis.UNKNOWN,
            RehabBasis.USER_ENTERED,
            RehabBasis.PER_SQFT_ESTIMATE,
        )
        if heavy and weak_basis:
            flags.append(
                RiskFlag(
                    code="unrealistic_rehab_assumptions",
                    label="Heavy rehab on a weak estimate",
                    severity=RiskSeverity.CRITICAL,
                    detail=(
                        f"Rehab is {rehab_ratio * 100:.0f}% of ARV but rests on a "
                        "rule-of-thumb or manual figure rather than a scope or bid."
                    ),
                    blocks_pursue=True,
                )
            )
        elif weak_basis:
            flags.append(
                RiskFlag(
                    code="rehab_estimate_unsupported",
                    label="Rehab estimate unsupported",
                    severity=RiskSeverity.WARNING,
                    detail="No scope of work or contractor bid supports this rehab figure.",
                )
            )
        elif heavy:
            flags.append(
                RiskFlag(
                    code="heavy_rehab",
                    label="Heavy rehab scope",
                    severity=RiskSeverity.WARNING,
                    detail=(
                        f"Rehab is {rehab_ratio * 100:.0f}% of ARV. Cost overruns scale "
                        "with scope."
                    ),
                )
            )

    # --- Operating expenses -------------------------------------------------
    #
    # Unknown taxes or insurance are treated as a deal-stopper rather than a
    # warning. On a typical single-family rental the two together run several
    # hundred dollars a month; leaving them out flips cash flow positive and
    # moves a deal from NOT MET to MET inside the buy box. A number that can
    # change the verdict on its own cannot be an advisory note.
    blocking_expenses = inputs.assumptions.blocking_unknown_expenses()
    if blocking_expenses:
        labels = ", ".join(
            _EXPENSE_LABELS.get(path, path) for path in blocking_expenses
        )
        flags.append(
            RiskFlag(
                code="operating_expenses_unknown",
                label="Operating expenses not established",
                severity=RiskSeverity.CRITICAL,
                detail=(
                    f"No figure has been entered for {labels}. Atlas leaves unknown "
                    "expenses out of the arithmetic rather than guessing, so every "
                    "cash-flow and profit figure above is overstated. Enter the real "
                    "numbers — or an explicit 0 where the expense does not apply — "
                    "before treating this analysis as decision-grade."
                ),
                blocks_pursue=True,
            )
        )

    if not inputs.evidence.property_visited:
        flags.append(
            RiskFlag(
                code="property_not_inspected",
                label="Property not walked",
                severity=RiskSeverity.WARNING,
                detail=(
                    "Nobody has been inside. Condition risk is unpriced until someone "
                    "walks the property."
                ),
            )
        )

    if not inputs.evidence.title_reviewed:
        flags.append(
            RiskFlag(
                code="title_not_reviewed",
                label="Title not yet reviewed",
                severity=RiskSeverity.WARNING,
                detail=(
                    "No title search has been run. This is normal at the analysis "
                    "stage, but it must clear before closing."
                ),
            )
        )

    # --- Age / condition ----------------------------------------------------
    year_built = inputs.property_facts.year_built
    if (
        year_built is not None
        and year_built < OLD_CONSTRUCTION_YEAR
        and not inputs.evidence.inspection_completed
    ):
        flags.append(
            RiskFlag(
                code="older_construction_uninspected",
                label="Pre-1960 construction, no inspection",
                severity=RiskSeverity.WARNING,
                detail=(
                    f"Built in {year_built}. Knob-and-tube wiring, cast-iron plumbing, "
                    "lead paint and asbestos are common in this vintage."
                ),
            )
        )

    # --- Deal-level economics ----------------------------------------------
    if comparison.recommended is None:
        flags.append(
            RiskFlag(
                code="no_viable_strategy",
                label="No viable strategy",
                severity=RiskSeverity.CRITICAL,
                detail="No exit could be evaluated with the information available.",
                blocks_pursue=True,
            )
        )
    elif comparison.viable_exit_count == 0:
        flags.append(
            RiskFlag(
                code="no_exit_meets_buy_box",
                label="No exit clears the buy box",
                severity=RiskSeverity.WARNING,
                detail=(
                    "Every strategy computes, but none meets its own minimum return "
                    "criteria at this price."
                ),
            )
        )
    elif comparison.viable_exit_count == 1:
        flags.append(
            RiskFlag(
                code="single_exit",
                label="Single viable exit",
                severity=RiskSeverity.WARNING,
                detail=(
                    "Only one strategy clears the buy box. If it stops working there "
                    "is no fallback."
                ),
            )
        )

    if comparison.overall_confidence == Confidence.LOW:
        flags.append(
            RiskFlag(
                code="low_overall_confidence",
                label="Low confidence in the inputs",
                severity=RiskSeverity.WARNING,
                detail=(
                    "The weakest supporting input is LOW confidence, so the whole "
                    "analysis inherits that uncertainty."
                ),
            )
        )

    return flags


def collect_declared_flags(codes: List[str]) -> List[RiskFlag]:
    """Resolve user-declared flag codes against the registry.

    An unrecognised code is kept as a warning rather than dropped: a risk
    someone bothered to record must not vanish because Atlas lacks a definition
    for it.
    """
    flags: List[RiskFlag] = []
    for code in codes:
        known = DECLARABLE_FLAGS.get(code)
        if known is not None:
            flags.append(known)
        else:
            flags.append(
                RiskFlag(
                    code=code,
                    label=code.replace("_", " ").capitalize(),
                    severity=RiskSeverity.WARNING,
                    detail="User-declared risk with no standard definition in Atlas.",
                    source="declared",
                )
            )
    return flags


def all_risk_flags(
    inputs: DealInputs, comparison: StrategyComparison
) -> List[RiskFlag]:
    """Every flag for this deal, most severe first."""
    flags = derive_risk_flags(inputs, comparison) + collect_declared_flags(
        inputs.risk_flags
    )
    order = {RiskSeverity.CRITICAL: 0, RiskSeverity.WARNING: 1, RiskSeverity.INFO: 2}
    # Deduplicate by code, keeping the first (declared flags win on tie).
    seen: Dict[str, RiskFlag] = {}
    for flag in flags:
        if flag.code not in seen:
            seen[flag.code] = flag
    return sorted(seen.values(), key=lambda f: order[f.severity])
