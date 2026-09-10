"""The boundary where a stored assumption blob's meaning is decided.

Operating expenses became tri-state in engine 0.3. Before that, a stored ``0``
for taxes or insurance meant "nobody filled this in"; now it means "this
property genuinely has none". The same three characters, two opposite claims.

Everything here exists so that reading an analysis back never changes what it
said. The interesting cases are all at the seams: a legacy buy box merged with
a fresh override, a re-run of an old analysis, a client that forgets to declare
its version.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from atlas_financial_engine import ASSUMPTIONS_SCHEMA_VERSION

from atlas_api.services.analysis import resolve_assumptions

CURRENT = {"schema_version": ASSUMPTIONS_SCHEMA_VERSION}


class TestStoredData:
    def test_a_legacy_zero_is_read_as_unknown(self):
        """Written when 0 was the only way to say "not entered"."""
        legacy = {"rental": {"annual_taxes": "0", "annual_insurance": "0"}}
        a = resolve_assumptions(legacy, None)
        assert a.rental.annual_taxes is None
        assert a.rental.blocking_unknowns() == ["annual_taxes", "annual_insurance"]

    def test_a_legacy_figure_survives_untouched(self):
        a = resolve_assumptions({"rental": {"annual_taxes": "3200"}}, None)
        assert str(a.rental.annual_taxes) == "3200"

    def test_a_current_zero_is_read_as_zero(self):
        current = dict(CURRENT, rental={"annual_taxes": "0"})
        assert resolve_assumptions(current, None).rental.annual_taxes == 0


class TestMergingAcrossVersions:
    def test_a_fresh_override_is_not_dragged_into_legacy_semantics(self):
        """The case that motivated migrating each source separately.

        A buy box saved before the change, plus a deliberate zero entered
        today. Migrating the merged result would apply the old blob's meaning
        to the new value and quietly discard the user's answer.
        """
        legacy_defaults = {"rental": {"annual_taxes": "2400", "annual_insurance": "0"}}
        todays_override = dict(CURRENT, rental={"annual_insurance": "0"})

        a = resolve_assumptions(legacy_defaults, todays_override)
        assert a.rental.annual_insurance == 0, "the user's explicit zero was lost"
        assert str(a.rental.annual_taxes) == "2400"

    def test_the_legacy_half_still_gets_legacy_treatment(self):
        """The other direction: the old blob's ambiguous zero stays unknown
        when the override says nothing about it."""
        legacy_defaults = {"rental": {"annual_taxes": "0"}}
        todays_override = dict(CURRENT, flip={"holding_months": 9})

        a = resolve_assumptions(legacy_defaults, todays_override)
        assert a.rental.annual_taxes is None
        assert a.flip.holding_months == 9

    def test_an_override_wins_over_a_saved_default(self):
        a = resolve_assumptions(
            dict(CURRENT, rental={"annual_taxes": "2400"}),
            dict(CURRENT, rental={"annual_taxes": "3100"}),
        )
        assert str(a.rental.annual_taxes) == "3100"


class TestUndeclaredVersion:
    def test_an_undeclared_version_is_treated_as_legacy(self):
        """Conservative on purpose.

        Every blob written before version 1 lacks the key, so defaulting to
        "current" would silently reinterpret all of them. Defaulting to legacy
        can only inconvenience a caller who omits the version, and it does so
        loudly: the value comes back unknown and the analysis says so.
        """
        a = resolve_assumptions(None, {"rental": {"annual_taxes": "0"}})
        assert a.rental.annual_taxes is None


class TestPersistence:
    def test_a_saved_analysis_records_the_version_it_was_written_under(
        self, client, property_id, analysis_payload
    ):
        response = client.post(
            f"/api/properties/{property_id}/analyses", json=analysis_payload
        )
        assert response.status_code == 201
        stored = response.json()["inputs"]["assumptions"]
        assert stored["schema_version"] == ASSUMPTIONS_SCHEMA_VERSION

    def test_the_version_travels_in_the_response(self, client, analysis_payload):
        response = client.post("/api/analyze", json=analysis_payload)
        assert response.status_code == 200
        assert (
            response.json()["inputs"]["assumptions"]["schema_version"]
            == ASSUMPTIONS_SCHEMA_VERSION
        )


class TestExplicitZeroEndToEnd:
    def test_an_explicit_zero_clears_the_blocking_flag(self, client, analysis_payload):
        """A property with no HOA and no insurable structure is unusual but
        real, and saying so must be possible without inventing a figure."""
        payload = dict(analysis_payload)
        payload["assumptions"] = dict(
            CURRENT,
            rental={
                "annual_taxes": "0",
                "annual_insurance": "0",
                "monthly_hoa": "0",
            },
            holding={"annual_taxes": "0", "annual_insurance": "0"},
        )
        body = client.post("/api/analyze", json=payload).json()
        codes = [f["code"] for f in body["scoring"]["risk_flags"]]
        assert "operating_expenses_unknown" not in codes

    def test_omitting_them_raises_the_blocking_flag(self, client, analysis_payload):
        payload = dict(analysis_payload)
        payload.pop("assumptions", None)
        body = client.post("/api/analyze", json=payload).json()
        flag = next(
            f
            for f in body["scoring"]["risk_flags"]
            if f["code"] == "operating_expenses_unknown"
        )
        assert flag["blocks_pursue"] is True
        assert body["scoring"]["verdict"] == "HUMAN_REVIEW_REQUIRED"

    def test_the_missing_expenses_are_named_for_the_ui(self, client, analysis_payload):
        payload = dict(analysis_payload)
        payload.pop("assumptions", None)
        body = client.post("/api/analyze", json=payload).json()
        assert "rental.annual_taxes" in body["missing_information"]
        assert "holding.annual_insurance" in body["missing_information"]


class TestClientAgreement:
    def test_the_web_client_declares_the_same_version(self):
        """A constant duplicated across two languages will drift.

        If the browser sends a version the API does not recognise, or keeps
        sending an old one, the failure is silent: explicit zeros quietly come
        back as unknown. Cheaper to assert than to debug.
        """
        source = (
            Path(__file__).resolve().parents[3] / "apps" / "web" / "lib" / "assumptions.ts"
        ).read_text()
        match = re.search(
            r"export const ASSUMPTIONS_SCHEMA_VERSION\s*=\s*(\d+)", source
        )
        assert match, "the web client no longer declares ASSUMPTIONS_SCHEMA_VERSION"
        assert int(match.group(1)) == ASSUMPTIONS_SCHEMA_VERSION


@pytest.fixture
def property_id(client) -> str:
    response = client.post(
        "/api/properties", json={"address": "1 Schema Version Way", "state": "TN"}
    )
    assert response.status_code == 201
    return response.json()["id"]
