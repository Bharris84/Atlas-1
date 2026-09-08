"""Individual strategy models. Each takes ``DealInputs`` and returns a
``StrategyResult`` so the strategy engine can compare them on equal terms."""

from .brrrr import analyze_brrrr
from .buy_hold import analyze_buy_hold, build_operating_statement
from .flip import analyze_flip
from .seller_finance import analyze_seller_finance
from .wholesale import analyze_wholesale

__all__ = [
    "analyze_brrrr",
    "analyze_buy_hold",
    "analyze_flip",
    "analyze_seller_finance",
    "analyze_wholesale",
    "build_operating_statement",
]
