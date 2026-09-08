"""Data provider abstraction.

The guarantee under test: Atlas works with no provider configured, and every
value that does come from a provider carries its provenance.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List

import pytest

from atlas_data_providers import (
    NullProvider,
    ProviderRequestError,
    ProviderUnavailable,
    RentCastProvider,
    available_providers,
    describe_providers,
    get_provider,
    register_provider,
)


class _FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _FakeClient:
    """Routes requests by URL suffix so one client can serve a whole lookup."""

    def __init__(self, routes: Dict[str, _FakeResponse]) -> None:
        self.routes = routes
        self.calls: List[Dict[str, Any]] = []

    def get(self, url: str, headers=None, params=None):
        self.calls.append({"url": url, "headers": headers or {}, "params": params or {}})
        for suffix, response in self.routes.items():
            if url.endswith(suffix):
                return response
        return _FakeResponse(None, status_code=404)


PROPERTY_PAYLOAD = [
    {
        "id": "prop-1",
        "formattedAddress": "412 Magnolia St, Chattanooga, TN 37402",
        "city": "Chattanooga",
        "state": "TN",
        "zipCode": "37402",
        "county": "Hamilton",
        "propertyType": "Single Family",
        "bedrooms": 3,
        "bathrooms": 2,
        "squareFootage": 1450,
        "yearBuilt": 1998,
        "latitude": 35.0456,
        "longitude": -85.3097,
        "owner": {
            "names": ["Example Holdings LLC"],
            "type": "Organization",
            "ownerOccupied": False,
            "mailingAddress": {"formattedAddress": "PO Box 10, Nashville, TN"},
        },
    }
]

VALUE_PAYLOAD = {
    "price": 251000,
    "priceRangeLow": 242000,
    "priceRangeHigh": 260000,
    "comparables": [
        {
            "id": "comp-1",
            "formattedAddress": "418 Magnolia St",
            "price": 248000,
            "squareFootage": 1400,
            "bedrooms": 3,
            "bathrooms": 2,
            "correlation": 0.93,
            "distance": 0.1,
            "removedDate": "2025-06-01",
        }
    ],
}

RENT_PAYLOAD = {"rent": 1825, "rentRangeLow": 1700, "rentRangeHigh": 1950}


def _configured_provider(routes: Dict[str, _FakeResponse]) -> RentCastProvider:
    return RentCastProvider(api_key="test-key", client=_FakeClient(routes))


class TestNullProvider:
    def test_is_always_available(self):
        assert NullProvider().is_configured is True

    def test_returns_nothing_and_says_what_is_missing(self):
        """Distinguishes "no provider connected" from "this house has no comps"."""
        result = NullProvider().lookup("412 Magnolia St")
        assert result.property is None
        assert result.comps == []
        assert "comparable_sales" in result.unavailable

    def test_accepts_and_ignores_configuration(self):
        assert NullProvider(api_key="ignored", base_url="ignored").is_configured is True


class TestRegistry:
    def test_unconfigured_provider_falls_back_to_null(self):
        """A missing API key must never take the application down."""
        assert get_provider("rentcast").name == "none"

    def test_unknown_provider_falls_back_to_null(self):
        assert get_provider("a-provider-that-does-not-exist").name == "none"

    def test_no_provider_requested_falls_back_to_null(self):
        assert get_provider(None).name == "none"

    def test_configured_provider_is_returned(self):
        provider = get_provider("rentcast", api_key="test-key")
        assert provider.name == "rentcast"

    def test_new_providers_can_be_registered(self):
        """The interface is the extension point for ATTOM, MLS, county records."""
        register_provider("fake_county_records", NullProvider)
        assert "fake_county_records" in available_providers()

    def test_describe_reports_status_without_the_key(self):
        described = {p["name"]: p for p in describe_providers("secret-key-value")}
        assert described["rentcast"]["configured"] is True
        assert "secret-key-value" not in str(described)

    def test_describe_explains_that_manual_entry_still_works(self):
        described = {p["name"]: p for p in describe_providers(None)}
        assert described["rentcast"]["configured"] is False
        assert "manually entered data" in described["rentcast"]["detail"]


class TestRentCastConfiguration:
    def test_without_a_key_it_is_unconfigured(self):
        assert RentCastProvider(api_key=None).is_configured is False

    def test_without_a_key_a_direct_request_explains_the_fallback(self):
        with pytest.raises(ProviderUnavailable) as exc:
            RentCastProvider(api_key=None)._get("properties", {"address": "x"})
        assert "manual entry" in str(exc.value)

    def test_without_a_key_a_lookup_degrades_instead_of_raising(self):
        """Callers get an empty result they can render, not an exception."""
        lookup = RentCastProvider(api_key=None).lookup("412 Magnolia St")
        assert lookup.property is None
        assert lookup.value is None
        assert "property_details" in lookup.unavailable

    def test_the_key_is_sent_as_a_header_not_a_query_parameter(self):
        """A key in a URL ends up in logs and referrers."""
        client = _FakeClient({"/properties": _FakeResponse(PROPERTY_PAYLOAD)})
        RentCastProvider(api_key="test-key", client=client).lookup("412 Magnolia St")
        call = client.calls[0]
        assert call["headers"]["X-Api-Key"] == "test-key"
        assert "test-key" not in str(call["params"])

    def test_declares_its_capabilities(self):
        capabilities = RentCastProvider(api_key="k").capabilities
        assert "value_estimate" in capabilities
        assert "comparable_sales" in capabilities


class TestRentCastParsing:
    @pytest.fixture
    def provider(self):
        return _configured_provider(
            {
                "/properties": _FakeResponse(PROPERTY_PAYLOAD),
                "/avm/value": _FakeResponse(VALUE_PAYLOAD),
                "/avm/rent/long-term": _FakeResponse(RENT_PAYLOAD),
            }
        )

    def test_property_details(self, provider):
        record = provider.lookup("412 Magnolia St").property
        assert record.city == "Chattanooga"
        assert record.state == "TN"
        assert record.bedrooms == Decimal("3")
        assert record.square_feet == Decimal("1450")
        assert record.year_built == 1998

    def test_value_estimate_with_its_range(self, provider):
        value = provider.lookup("412 Magnolia St").value
        assert value.value == Decimal("251000")
        assert value.value_low == Decimal("242000")
        assert value.value_high == Decimal("260000")

    def test_an_automated_valuation_is_marked_low_confidence(self, provider):
        """An AVM cannot see condition, which is the basis of a value-add deal."""
        assert provider.lookup("412 Magnolia St").value.provenance.confidence == "LOW"

    def test_rent_estimate(self, provider):
        rent = provider.lookup("412 Magnolia St").rent
        assert rent.rent == Decimal("1825")
        assert rent.provenance.confidence == "MEDIUM"

    def test_comps_carry_similarity_and_computed_price_per_foot(self, provider):
        comp = provider.lookup("412 Magnolia St").comps[0]
        assert comp.sale_price == Decimal("248000")
        assert comp.similarity_score == Decimal("0.93")
        assert comp.price_per_square_foot == Decimal("248000") / Decimal("1400")

    def test_owner_occupancy_is_recorded_as_an_observation(self, provider):
        """Absentee is a classification. It is not a claim about motivation."""
        owner = provider.lookup("412 Magnolia St").owner
        assert owner.occupancy_indicator == "absentee"
        assert owner.entity_type == "entity"

    def test_every_record_carries_provenance(self, provider):
        lookup = provider.lookup("412 Magnolia St")
        for record in (lookup.property, lookup.owner, lookup.value, lookup.rent):
            assert record.provenance is not None
            assert record.provenance.provider == "rentcast"
            assert record.provenance.retrieved_at is not None

    def test_lookup_serialises_for_storage(self, provider):
        import json

        payload = provider.lookup("412 Magnolia St").to_dict()
        assert json.loads(json.dumps(payload))["property"]["city"] == "Chattanooga"


class TestRentCastFailureHandling:
    def test_one_failed_endpoint_does_not_lose_the_others(self):
        """A missing rent estimate must not discard the property record."""
        provider = _configured_provider(
            {
                "/properties": _FakeResponse(PROPERTY_PAYLOAD),
                "/avm/value": _FakeResponse(None, status_code=500),
            }
        )
        lookup = provider.lookup("412 Magnolia St")
        assert lookup.property is not None
        assert lookup.value is None
        assert "value_estimate" in lookup.unavailable

    def test_a_rejected_key_is_reported_as_unavailable(self):
        provider = _configured_provider({"/properties": _FakeResponse(None, 401)})
        lookup = provider.lookup("412 Magnolia St")
        assert lookup.property is None
        assert "property_details" in lookup.unavailable

    def test_rate_limiting_is_surfaced_clearly(self):
        provider = RentCastProvider(
            api_key="k", client=_FakeClient({"/markets": _FakeResponse(None, 429)})
        )
        with pytest.raises(ProviderRequestError) as exc:
            provider._get("markets", {"zipCode": "37402"})
        assert "rate limit" in str(exc.value).lower()

    def test_a_network_failure_is_unavailable_not_a_crash(self):
        class _Broken:
            def get(self, *args, **kwargs):
                raise ConnectionError("network down")

        provider = RentCastProvider(api_key="k", client=_Broken())
        lookup = provider.lookup("412 Magnolia St")
        assert lookup.property is None
        assert lookup.unavailable

    def test_unknown_address_returns_nothing_rather_than_guessing(self):
        provider = _configured_provider({})
        lookup = provider.lookup("nowhere at all")
        assert lookup.property is None
        assert lookup.value is None


class TestMarketStats:
    def test_market_stats_are_parsed(self):
        provider = RentCastProvider(
            api_key="k",
            client=_FakeClient(
                {
                    "/markets": _FakeResponse(
                        {
                            "saleData": {
                                "medianPrice": 265000,
                                "averageDaysOnMarket": 34,
                                "totalListings": 120,
                            },
                            "rentalData": {"medianRent": 1750},
                        }
                    )
                }
            ),
        )
        stats = provider.get_market_stats("37402")
        assert stats.median_sale_price == Decimal("265000")
        assert stats.median_rent == Decimal("1750")
        assert stats.average_days_on_market == 34

    def test_null_provider_has_no_market_stats(self):
        assert NullProvider().get_market_stats("37402") is None
