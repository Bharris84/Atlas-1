"""Property data provider abstraction.

Business logic never talks to RentCast, ATTOM, or an MLS directly. It talks to
this interface, so a provider can be swapped, added, or removed without
touching an underwriting rule.

Two guarantees hold for every provider:

1. **Nothing is required.** With no provider configured, Atlas falls back to
   the null provider and the financial engine still works on manually entered
   data. External data is an enrichment, never a dependency.
2. **Everything carries provenance.** Each returned record records which
   provider produced it, when, from what record id, and how confident it is.
   Without that, Atlas could not tell a fact from an estimate.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Generic, List, Optional, TypeVar


class ProviderError(RuntimeError):
    """Base class for provider failures."""


class ProviderUnavailable(ProviderError):
    """The provider is not configured or cannot be reached.

    Callers are expected to catch this and continue with manual data — it is a
    normal operating condition, not an exceptional one.
    """


class ProviderRequestError(ProviderError):
    """The provider was reachable but rejected or failed the request."""


@dataclass(frozen=True)
class Provenance:
    """Where a piece of data came from."""

    provider: str
    retrieved_at: datetime
    provider_record_id: Optional[str] = None
    source_url: Optional[str] = None
    # HIGH / MEDIUM / LOW — how much weight the confidence engine should give it.
    confidence: str = "MEDIUM"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "retrieved_at": self.retrieved_at.isoformat(),
            "provider_record_id": self.provider_record_id,
            "source_url": self.source_url,
            "confidence": self.confidence,
        }


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


T = TypeVar("T")


@dataclass(frozen=True)
class Sourced(Generic[T]):
    """A value together with where it came from."""

    value: T
    provenance: Provenance

    def to_dict(self) -> Dict[str, Any]:
        value = self.value
        return {
            "value": str(value) if isinstance(value, Decimal) else value,
            "provenance": self.provenance.to_dict(),
        }


@dataclass(frozen=True)
class PropertyRecord:
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    county: Optional[str] = None
    parcel_apn: Optional[str] = None
    property_type: Optional[str] = None
    bedrooms: Optional[Decimal] = None
    bathrooms: Optional[Decimal] = None
    square_feet: Optional[Decimal] = None
    lot_size: Optional[Decimal] = None
    year_built: Optional[int] = None
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None
    last_sale_price: Optional[Decimal] = None
    last_sale_date: Optional[date] = None
    provenance: Optional[Provenance] = None

    def to_dict(self) -> Dict[str, Any]:
        return _asdict_strings(self)


@dataclass(frozen=True)
class OwnerRecord:
    owner_name: Optional[str] = None
    entity_type: Optional[str] = None
    mailing_address: Optional[str] = None
    ownership_start_date: Optional[date] = None
    estimated_equity: Optional[Decimal] = None
    estimated_mortgage: Optional[Decimal] = None
    # An observation of occupancy, never an inference about motivation.
    occupancy_indicator: Optional[str] = None
    provenance: Optional[Provenance] = None

    def to_dict(self) -> Dict[str, Any]:
        return _asdict_strings(self)


@dataclass(frozen=True)
class ValueEstimate:
    value: Optional[Decimal] = None
    value_low: Optional[Decimal] = None
    value_high: Optional[Decimal] = None
    provenance: Optional[Provenance] = None

    def to_dict(self) -> Dict[str, Any]:
        return _asdict_strings(self)


@dataclass(frozen=True)
class RentEstimate:
    rent: Optional[Decimal] = None
    rent_low: Optional[Decimal] = None
    rent_high: Optional[Decimal] = None
    provenance: Optional[Provenance] = None

    def to_dict(self) -> Dict[str, Any]:
        return _asdict_strings(self)


@dataclass(frozen=True)
class CompRecord:
    address: Optional[str] = None
    distance_miles: Optional[Decimal] = None
    sale_price: Optional[Decimal] = None
    sale_date: Optional[date] = None
    bedrooms: Optional[Decimal] = None
    bathrooms: Optional[Decimal] = None
    square_feet: Optional[Decimal] = None
    lot_size: Optional[Decimal] = None
    year_built: Optional[int] = None
    property_type: Optional[str] = None
    condition: Optional[str] = None
    price_per_square_foot: Optional[Decimal] = None
    similarity_score: Optional[Decimal] = None
    provenance: Optional[Provenance] = None

    def to_dict(self) -> Dict[str, Any]:
        return _asdict_strings(self)


@dataclass(frozen=True)
class ListingRecord:
    address: Optional[str] = None
    listing_price: Optional[Decimal] = None
    status: Optional[str] = None
    days_on_market: Optional[int] = None
    listed_date: Optional[date] = None
    provenance: Optional[Provenance] = None

    def to_dict(self) -> Dict[str, Any]:
        return _asdict_strings(self)


@dataclass(frozen=True)
class MarketStats:
    zip_code: Optional[str] = None
    median_sale_price: Optional[Decimal] = None
    median_rent: Optional[Decimal] = None
    average_days_on_market: Optional[int] = None
    sale_count: Optional[int] = None
    provenance: Optional[Provenance] = None

    def to_dict(self) -> Dict[str, Any]:
        return _asdict_strings(self)


@dataclass(frozen=True)
class PropertyLookup:
    """Everything a provider could return for one address, in one object."""

    property: Optional[PropertyRecord] = None
    owner: Optional[OwnerRecord] = None
    value: Optional[ValueEstimate] = None
    rent: Optional[RentEstimate] = None
    comps: List[CompRecord] = field(default_factory=list)
    listing: Optional[ListingRecord] = None
    market: Optional[MarketStats] = None
    # Human-readable notes about what could NOT be retrieved. Surfaced in the
    # UI so a gap in the data is visible rather than silently absent.
    unavailable: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "property": self.property.to_dict() if self.property else None,
            "owner": self.owner.to_dict() if self.owner else None,
            "value": self.value.to_dict() if self.value else None,
            "rent": self.rent.to_dict() if self.rent else None,
            "comps": [c.to_dict() for c in self.comps],
            "listing": self.listing.to_dict() if self.listing else None,
            "market": self.market.to_dict() if self.market else None,
            "unavailable": list(self.unavailable),
        }


def _asdict_strings(obj: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in obj.__dict__.items():
        if key == "provenance":
            result[key] = value.to_dict() if value else None
        elif isinstance(value, Decimal):
            result[key] = str(value)
        elif isinstance(value, (date, datetime)):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


class PropertyDataProvider(abc.ABC):
    """Interface every property data source implements."""

    name: str = "abstract"

    @property
    @abc.abstractmethod
    def is_configured(self) -> bool:
        """True when this provider has what it needs to make a request."""

    @property
    def capabilities(self) -> List[str]:
        """Which lookups this provider supports."""
        return []

    @abc.abstractmethod
    def lookup(self, address: str, **kwargs: Any) -> PropertyLookup:
        """Retrieve everything available for one address."""

    def get_property(self, address: str, **kwargs: Any) -> Optional[PropertyRecord]:
        return self.lookup(address, **kwargs).property

    def get_owner(self, address: str, **kwargs: Any) -> Optional[OwnerRecord]:
        return self.lookup(address, **kwargs).owner

    def get_value_estimate(self, address: str, **kwargs: Any) -> Optional[ValueEstimate]:
        return self.lookup(address, **kwargs).value

    def get_rent_estimate(self, address: str, **kwargs: Any) -> Optional[RentEstimate]:
        return self.lookup(address, **kwargs).rent

    def get_comps(self, address: str, **kwargs: Any) -> List[CompRecord]:
        return self.lookup(address, **kwargs).comps

    def get_listing(self, address: str, **kwargs: Any) -> Optional[ListingRecord]:
        return self.lookup(address, **kwargs).listing

    def get_market_stats(self, zip_code: str, **kwargs: Any) -> Optional[MarketStats]:
        return None
