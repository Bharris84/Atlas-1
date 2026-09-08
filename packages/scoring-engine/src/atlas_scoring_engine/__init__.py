"""Atlas scoring engine.

Turns a strategy comparison into a deal score, a set of risk flags, and a
verdict. Deterministic and separate from the financial engine so scoring policy
can change without touching the arithmetic.
"""

from .risk import (
    DECLARABLE_FLAGS,
    RiskFlag,
    all_risk_flags,
    collect_declared_flags,
    derive_risk_flags,
)
from .scoring import (
    DealScore,
    INVESTIGATE_THRESHOLD,
    PURSUE_THRESHOLD,
    ScoreComponent,
    ScoringWeights,
    compute_risk_score,
    score_deal,
)

__version__ = "0.1.0"

__all__ = [
    "DECLARABLE_FLAGS",
    "DealScore",
    "INVESTIGATE_THRESHOLD",
    "PURSUE_THRESHOLD",
    "RiskFlag",
    "ScoreComponent",
    "ScoringWeights",
    "all_risk_flags",
    "collect_declared_flags",
    "compute_risk_score",
    "derive_risk_flags",
    "score_deal",
    "__version__",
]
