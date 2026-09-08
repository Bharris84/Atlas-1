"""RentCast provider.

Retrieves property details, owner information, value and rent estimates,
comparable sales and listings.

The API key is read from the environment and used only here, in the backend.
It is never returned in a response and never reaches the browser. With no key
configured, ``is_configured`` is False and callers fall back to manual data —
which is a supported way to run Atlas, not a degraded one.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from .base import (
    CompRecord,
    ListingRecord,
    MarketStats,
    OwnerRecord,
    PropertyDataProvider,
    PropertyLookup,
    PropertyRecord,
    Provenance,
    ProviderRequestError,
    ProviderUnavailable,
    RentEstimate,
    ValueEstimate,
    now_utc,
)

logger = logging.getLogger("atlas.providers.rentcast")

DEFAULT_BASE_URL = "https://api.rentcast.io/v1"


def _dec(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _int(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _date(value: Any) -> Optional[date]:
    if not value:
        return None
    text = str(value)
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(text[: len(fmt) + 6], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


class RentCastProvider(PropertyDataProvider):
    name = "rentcast"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_seconds: float = 20.0,
        client: Any = None,
    ) -> None:
        self._api_key = api_key or os.getenv("RENTCAST_API_KEY")
        self._base_url = (base_url or os.getenv("RENTCAST_BASE_URL") or DEFAULT_BASE_URL).rstrip(
            "/"
        )
        self._timeout = timeout_seconds
        # Injectable so the provider can be exercised without network access.
        self._client = client

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    @property
    def capabilities(self) -> List[str]:
        return [
            "property_details",
            "owner_information",
            "value_estimate",
            "rent_estimate",
            "comparable_sales",
            "listings",
            "market_data",
        ]

    # --- HTTP ---------------------------------------------------------------

    def _get(self, path: str, params: Dict[str, Any]) -> Any:
        if not self.is_configured:
            raise ProviderUnavailable(
                "RentCast API key is not configured. Set RENTCAST_API_KEY to enable "
                "automatic property data, or continue with manual entry."
            )
        url = f"{self._base_url}/{path.lstrip('/')}"
        headers = {"X-Api-Key": self._api_key, "Accept": "application/json"}
        clean = {k: v for k, v in params.items() if v is not None}

        client = self._client
        if client is None:
            try:
                import httpx
            except ImportError as exc:  # pragma: no cover - packaging guard
                raise ProviderUnavailable("httpx is required for the RentCast provider") from exc
            with httpx.Client(timeout=self._timeout) as http:
                return self._send(http, url, headers, clean)
        return self._send(client, url, headers, clean)

    def _send(self, client: Any, url: str, headers: Dict[str, str], params: Dict[str, Any]) -> Any:
        try:
            response = client.get(url, headers=headers, params=params)
        except Exception as exc:  # network failure, DNS, timeout
            raise ProviderUnavailable(f"RentCast is unreachable: {exc}") from exc

        status = getattr(response, "status_code", 500)
        if status == 401 or status == 403:
            raise ProviderUnavailable("RentCast rejected the API key.")
        if status == 404:
            return None
        if status == 429:
            raise ProviderRequestError("RentCast rate limit reached. Try again shortly.")
        if status >= 400:
            raise ProviderRequestError(f"RentCast returned HTTP {status}.")
        try:
            return response.json()
        except Exception as exc:
            raise ProviderRequestError("RentCast returned a response that is not JSON.") from exc

    def _provenance(self, record_id: Optional[str], confidence: str) -> Provenance:
        return Provenance(
            provider=self.name,
            retrieved_at=now_utc(),
            provider_record_id=record_id,
            source_url=self._base_url,
            confidence=confidence,
        )

    # --- Lookups ------------------------------------------------------------

    def lookup(self, address: str, **kwargs: Any) -> PropertyLookup:
        """Retrieve everything RentCast has for an address.

        A failure in one endpoint does not lose the others: each section is
        attempted independently and anything unavailable is recorded by name so
        the gap is visible in the UI.
        """
        unavailable: List[str] = []

        property_record: Optional[PropertyRecord] = None
        owner_record: Optional[OwnerRecord] = None
        value: Optional[ValueEstimate] = None
        rent: Optional[RentEstimate] = None
        comps: List[CompRecord] = []
        listing: Optional[ListingRecord] = None

        try:
            records = self._get("properties", {"address": address}) or []
            if isinstance(records, dict):
                records = [records]
            if records:
                property_record = self._parse_property(records[0])
                owner_record = self._parse_owner(records[0])
            else:
                unavailable.append("property_details")
        except (ProviderUnavailable, ProviderRequestError) as exc:
            logger.info("rentcast property lookup unavailable: %s", exc)
            unavailable.append("property_details")

        try:
            payload = self._get("avm/value", {"address": address})
            if payload:
                value = self._parse_value(payload)
                comps = self._parse_comps(payload.get("comparables") or [])
            else:
                unavailable.append("value_estimate")
        except (ProviderUnavailable, ProviderRequestError) as exc:
            logger.info("rentcast value estimate unavailable: %s", exc)
            unavailable.append("value_estimate")

        try:
            payload = self._get("avm/rent/long-term", {"address": address})
            if payload:
                rent = self._parse_rent(payload)
            else:
                unavailable.append("rent_estimate")
        except (ProviderUnavailable, ProviderRequestError) as exc:
            logger.info("rentcast rent estimate unavailable: %s", exc)
            unavailable.append("rent_estimate")

        try:
            payload = self._get("listings/sale", {"address": address, "limit": 1})
            if isinstance(payload, list) and payload:
                listing = self._parse_listing(payload[0])
            elif isinstance(payload, dict) and payload:
                listing = self._parse_listing(payload)
        except (ProviderUnavailable, ProviderRequestError) as exc:
            logger.info("rentcast listing unavailable: %s", exc)
            unavailable.append("listing")

        return PropertyLookup(
            property=property_record,
            owner=owner_record,
            value=value,
            rent=rent,
            comps=comps,
            listing=listing,
            unavailable=unavailable,
        )

    def get_market_stats(self, zip_code: str, **kwargs: Any) -> Optional[MarketStats]:
        try:
            payload = self._get("markets", {"zipCode": zip_code})
        except (ProviderUnavailable, ProviderRequestError) as exc:
            logger.info("rentcast market stats unavailable: %s", exc)
            return None
        if not payload:
            return None
        sale = payload.get("saleData") or {}
        rental = payload.get("rentalData") or {}
        return MarketStats(
            zip_code=zip_code,
            median_sale_price=_dec(sale.get("medianPrice")),
            median_rent=_dec(rental.get("medianRent")),
            average_days_on_market=_int(sale.get("averageDaysOnMarket")),
            sale_count=_int(sale.get("totalListings")),
            provenance=self._provenance(zip_code, "MEDIUM"),
        )

    # --- Parsing ------------------------------------------------------------

    def _parse_property(self, data: Dict[str, Any]) -> PropertyRecord:
        return PropertyRecord(
            address=data.get("formattedAddress") or data.get("addressLine1"),
            city=data.get("city"),
            state=data.get("state"),
            zip_code=data.get("zipCode"),
            county=data.get("county"),
            parcel_apn=data.get("assessorID"),
            property_type=data.get("propertyType"),
            bedrooms=_dec(data.get("bedrooms")),
            bathrooms=_dec(data.get("bathrooms")),
            square_feet=_dec(data.get("squareFootage")),
            lot_size=_dec(data.get("lotSize")),
            year_built=_int(data.get("yearBuilt")),
            latitude=_dec(data.get("latitude")),
            longitude=_dec(data.get("longitude")),
            last_sale_price=_dec(data.get("lastSalePrice")),
            last_sale_date=_date(data.get("lastSaleDate")),
            # Recorded public attributes are strong data.
            provenance=self._provenance(data.get("id"), "HIGH"),
        )

    def _parse_owner(self, data: Dict[str, Any]) -> Optional[OwnerRecord]:
        owner = data.get("owner") or {}
        if not owner:
            return None
        names = owner.get("names") or []
        mailing = owner.get("mailingAddress") or {}
        return OwnerRecord(
            owner_name=", ".join(names) if names else None,
            entity_type="entity" if owner.get("type") == "Organization" else "individual",
            mailing_address=mailing.get("formattedAddress"),
            # Occupancy is an observation. Atlas records it and stops there —
            # it does not conclude anything about whether the owner wants to sell.
            occupancy_indicator=(
                "owner_occupied" if owner.get("ownerOccupied") else "absentee"
            )
            if owner.get("ownerOccupied") is not None
            else None,
            provenance=self._provenance(data.get("id"), "MEDIUM"),
        )

    def _parse_value(self, data: Dict[str, Any]) -> ValueEstimate:
        return ValueEstimate(
            value=_dec(data.get("price")),
            value_low=_dec(data.get("priceRangeLow")),
            value_high=_dec(data.get("priceRangeHigh")),
            # An automated valuation is LOW confidence by policy: an AVM cannot
            # see condition, which is the whole basis of a value-add deal.
            provenance=self._provenance(None, "LOW"),
        )

    def _parse_rent(self, data: Dict[str, Any]) -> RentEstimate:
        return RentEstimate(
            rent=_dec(data.get("rent")),
            rent_low=_dec(data.get("rentRangeLow")),
            rent_high=_dec(data.get("rentRangeHigh")),
            provenance=self._provenance(None, "MEDIUM"),
        )

    def _parse_comps(self, raw: List[Dict[str, Any]]) -> List[CompRecord]:
        comps: List[CompRecord] = []
        for item in raw:
            price = _dec(item.get("price"))
            sqft = _dec(item.get("squareFootage"))
            comps.append(
                CompRecord(
                    address=item.get("formattedAddress"),
                    distance_miles=_dec(item.get("distance")),
                    sale_price=price,
                    sale_date=_date(item.get("removedDate") or item.get("listedDate")),
                    bedrooms=_dec(item.get("bedrooms")),
                    bathrooms=_dec(item.get("bathrooms")),
                    square_feet=sqft,
                    lot_size=_dec(item.get("lotSize")),
                    year_built=_int(item.get("yearBuilt")),
                    property_type=item.get("propertyType"),
                    price_per_square_foot=(
                        price / sqft if price is not None and sqft else None
                    ),
                    similarity_score=_dec(item.get("correlation")),
                    provenance=self._provenance(item.get("id"), "MEDIUM"),
                )
            )
        return comps

    def _parse_listing(self, data: Dict[str, Any]) -> ListingRecord:
        return ListingRecord(
            address=data.get("formattedAddress"),
            listing_price=_dec(data.get("price")),
            status=data.get("status"),
            days_on_market=_int(data.get("daysOnMarket")),
            listed_date=_date(data.get("listedDate")),
            provenance=self._provenance(data.get("id"), "HIGH"),
        )
