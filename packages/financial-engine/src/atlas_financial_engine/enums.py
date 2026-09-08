"""Shared vocabulary for the financial engine."""

from __future__ import annotations

from enum import Enum


class Strategy(str, Enum):
    WHOLESALE = "wholesale"
    FLIP = "flip"
    BUY_HOLD = "buy_hold"
    BRRRR = "brrrr"
    SELLER_FINANCE = "seller_finance"


class Confidence(str, Enum):
    """Confidence in an estimate. Ordered LOW < MEDIUM < HIGH."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

    @property
    def rank(self) -> int:
        return {"LOW": 0, "MEDIUM": 1, "HIGH": 2}[self.value]

    @classmethod
    def weakest(cls, *values: "Confidence") -> "Confidence":
        """The chain is only as strong as its weakest link."""
        present = [v for v in values if v is not None]
        if not present:
            return cls.LOW
        return min(present, key=lambda c: c.rank)


class Assertion(str, Enum):
    """Epistemic status of a data point.

    Atlas never blurs these together. A number is either something we verified,
    something we estimated, something we inferred from other facts, or something
    we simply do not know.
    """

    FACT = "FACT"
    ESTIMATE = "ESTIMATE"
    INFERENCE = "INFERENCE"
    UNKNOWN = "UNKNOWN"


class FinancingMethod(str, Enum):
    CASH = "cash"
    HARD_MONEY = "hard_money"
    CONVENTIONAL = "conventional"
    PRIVATE = "private"
    SELLER = "seller"


class Verdict(str, Enum):
    PURSUE = "PURSUE"
    INVESTIGATE = "INVESTIGATE"
    PASS = "PASS"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"


class RiskSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class ValueBasis(str, Enum):
    """How an ARV / value estimate was derived. Drives the confidence engine."""

    COMPARABLE_SALES = "comparable_sales"
    AUTOMATED_VALUATION = "automated_valuation"
    APPRAISAL = "appraisal"
    BROKER_OPINION = "broker_opinion"
    LIST_PRICE = "list_price"
    USER_ENTERED = "user_entered"
    UNKNOWN = "unknown"


class RehabBasis(str, Enum):
    """How a rehab number was derived."""

    CONTRACTOR_BID = "contractor_bid"
    DETAILED_SCOPE = "detailed_scope"
    WALKTHROUGH = "walkthrough"
    PER_SQFT_ESTIMATE = "per_sqft_estimate"
    USER_ENTERED = "user_entered"
    UNKNOWN = "unknown"


class RentBasis(str, Enum):
    RENT_ROLL = "rent_roll"
    LEASE_IN_PLACE = "lease_in_place"
    RENTAL_COMPS = "rental_comps"
    AUTOMATED_ESTIMATE = "automated_estimate"
    USER_ENTERED = "user_entered"
    UNKNOWN = "unknown"
