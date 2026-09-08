"""Atlas property data providers.

Business logic depends on ``PropertyDataProvider``, never on a vendor. Atlas
runs fully without any provider configured.
"""

from .base import (
    CompRecord,
    ListingRecord,
    MarketStats,
    OwnerRecord,
    PropertyDataProvider,
    PropertyLookup,
    PropertyRecord,
    Provenance,
    ProviderError,
    ProviderRequestError,
    ProviderUnavailable,
    RentEstimate,
    Sourced,
    ValueEstimate,
)
from .null_provider import NullProvider
from .registry import (
    available_providers,
    describe_providers,
    get_provider,
    register_provider,
)
from .rentcast import RentCastProvider

__version__ = "0.1.0"

__all__ = [
    "CompRecord",
    "ListingRecord",
    "MarketStats",
    "NullProvider",
    "OwnerRecord",
    "PropertyDataProvider",
    "PropertyLookup",
    "PropertyRecord",
    "Provenance",
    "ProviderError",
    "ProviderRequestError",
    "ProviderUnavailable",
    "RentCastProvider",
    "RentEstimate",
    "Sourced",
    "ValueEstimate",
    "available_providers",
    "describe_providers",
    "get_provider",
    "register_provider",
    "__version__",
]
