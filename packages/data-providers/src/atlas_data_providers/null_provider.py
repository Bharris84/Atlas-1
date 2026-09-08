"""The null provider.

Used when no external data source is configured. It is not a stub that pretends
to work: it returns nothing and says clearly what was unavailable, so the UI can
show "no data provider connected" instead of an empty result that looks like
"this property has no comps".

This is the provider that guarantees Atlas runs with zero API keys.
"""

from __future__ import annotations

from typing import Any, List, Optional

from .base import MarketStats, PropertyDataProvider, PropertyLookup

UNAVAILABLE_SECTIONS = [
    "property_details",
    "owner_information",
    "value_estimate",
    "rent_estimate",
    "comparable_sales",
    "listing",
    "market_data",
]


class NullProvider(PropertyDataProvider):
    name = "none"

    def __init__(self, **kwargs: Any) -> None:
        # Accepts and ignores whatever configuration the registry passes.
        # Providers are constructed generically, and the caller should not have
        # to know which one it is getting.
        pass

    @property
    def is_configured(self) -> bool:
        # Always "configured": doing nothing reliably requires no setup.
        return True

    @property
    def capabilities(self) -> List[str]:
        return []

    def lookup(self, address: str, **kwargs: Any) -> PropertyLookup:
        return PropertyLookup(unavailable=list(UNAVAILABLE_SECTIONS))

    def get_market_stats(self, zip_code: str, **kwargs: Any) -> Optional[MarketStats]:
        return None
