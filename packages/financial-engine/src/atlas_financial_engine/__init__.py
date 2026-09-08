"""Atlas deterministic financial engine.

The single source of truth for every number Atlas publishes. No part of this
package calls a language model, a network service or a database. Given the same
inputs it returns the same outputs, on any machine, forever — which is what
makes an analysis auditable months after it was run.
"""

from .assumptions import (
    Assumptions,
    BrrrrAssumptions,
    FinancingTerms,
    FlipAssumptions,
    HoldingCosts,
    PROVISIONAL_DEFAULTS_NOTE,
    RentalAssumptions,
    SellerFinanceAssumptions,
    StrategyRankingWeights,
    TransactionCosts,
    WholesaleAssumptions,
)
from .confidence import Evidence, assess_arv, assess_rehab, assess_rent
from .costs import ProjectCosts, compute_project_costs
from .enums import (
    Assertion,
    Confidence,
    FinancingMethod,
    RehabBasis,
    RentBasis,
    RiskSeverity,
    Strategy,
    ValueBasis,
    Verdict,
)
from .inputs import DealInputs, PropertyFacts, build_inputs
from .loans import (
    amortization_schedule,
    dscr,
    monthly_payment,
    remaining_balance,
    total_interest_paid,
)
from .money import D, money, ratio, safe_div
from .results import Criterion, StrategyResult
from .strategies.brrrr import analyze_brrrr
from .strategies.buy_hold import analyze_buy_hold, build_operating_statement
from .strategies.flip import analyze_flip
from .strategies.seller_finance import analyze_seller_finance
from .strategies.wholesale import analyze_wholesale
from .strategy_engine import (
    StrategyComparison,
    StrategyScore,
    analyze_all_strategies,
    score_strategy,
)

__version__ = "0.1.0"

__all__ = [
    "Assertion",
    "Assumptions",
    "BrrrrAssumptions",
    "Confidence",
    "Criterion",
    "D",
    "DealInputs",
    "Evidence",
    "FinancingMethod",
    "FinancingTerms",
    "FlipAssumptions",
    "HoldingCosts",
    "PROVISIONAL_DEFAULTS_NOTE",
    "ProjectCosts",
    "PropertyFacts",
    "RehabBasis",
    "RentBasis",
    "RentalAssumptions",
    "RiskSeverity",
    "SellerFinanceAssumptions",
    "Strategy",
    "StrategyComparison",
    "StrategyRankingWeights",
    "StrategyResult",
    "StrategyScore",
    "TransactionCosts",
    "ValueBasis",
    "Verdict",
    "WholesaleAssumptions",
    "amortization_schedule",
    "analyze_all_strategies",
    "analyze_brrrr",
    "analyze_buy_hold",
    "analyze_flip",
    "analyze_seller_finance",
    "analyze_wholesale",
    "assess_arv",
    "assess_rehab",
    "assess_rent",
    "build_inputs",
    "build_operating_statement",
    "compute_project_costs",
    "dscr",
    "money",
    "monthly_payment",
    "ratio",
    "remaining_balance",
    "safe_div",
    "score_strategy",
    "total_interest_paid",
    "__version__",
]
