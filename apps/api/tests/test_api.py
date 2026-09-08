"""API behaviour.

Covers the V0.1 definition of done end to end: create a property, analyse it
across every strategy, change an assumption, see the numbers move, save it,
and reopen it later unchanged.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest


class TestSystem:
    def test_health(self, client):
        assert client.get("/api/health").json()["status"] == "ok"

    def test_status_reports_configuration_without_leaking_keys(
        self, client, monkeypatch
    ):
        """Status says whether a key exists. It never says what the key is."""
        from atlas_api.config import get_settings

        get_settings.cache_clear()
        monkeypatch.setenv("RENTCAST_API_KEY", "rc-secret-value-must-not-leak")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret-value-must-not-leak")
        try:
            body = client.get("/api/status").json()
            assert body["database"] == "sqlite"
            assert body["authentication"] == "development"
            serialised = str(body)
            assert "rc-secret-value-must-not-leak" not in serialised
            assert "sk-secret-value-must-not-leak" not in serialised
            # It does report that the provider is now connected.
            providers = {p["name"]: p for p in body["data_providers"]}
            assert providers["rentcast"]["configured"] is True
        finally:
            get_settings.cache_clear()

    def test_status_says_atlas_works_without_a_data_provider(self, client):
        providers = {p["name"]: p for p in client.get("/api/status").json()["data_providers"]}
        assert providers["rentcast"]["configured"] is False
        assert "manually entered data" in providers["rentcast"]["detail"]


class TestProperties:
    def test_create_and_read(self, client, property_payload):
        created = client.post("/api/properties", json=property_payload).json()
        assert created["address"] == property_payload["address"]
        assert created["state"] == "TN"

        fetched = client.get(f"/api/properties/{created['id']}").json()
        assert fetched["id"] == created["id"]

    def test_state_is_normalised_to_uppercase(self, client, property_payload):
        property_payload["state"] = "tn"
        assert client.post("/api/properties", json=property_payload).json()["state"] == "TN"

    def test_list_and_search(self, client, created_property):
        assert len(client.get("/api/properties").json()) == 1
        assert len(client.get("/api/properties?search=magnolia").json()) == 1
        assert len(client.get("/api/properties?search=nowhere").json()) == 0

    def test_filter_by_state(self, client, created_property):
        assert len(client.get("/api/properties?state=TN").json()) == 1
        assert len(client.get("/api/properties?state=FL").json()) == 0

    def test_update(self, client, created_property):
        response = client.patch(
            f"/api/properties/{created_property['id']}",
            json={"property_status": "under_contract", "estimated_value": "265000"},
        )
        assert response.json()["property_status"] == "under_contract"
        assert response.json()["estimated_value"] == "265000.00"

    def test_delete(self, client, created_property):
        assert client.delete(f"/api/properties/{created_property['id']}").status_code == 204
        assert client.get(f"/api/properties/{created_property['id']}").status_code == 404

    def test_unknown_property_is_404(self, client):
        assert client.get(f"/api/properties/{uuid.uuid4()}").status_code == 404


class TestValidation:
    def test_rejects_invalid_state_length(self, client, property_payload):
        property_payload["state"] = "TENN"
        assert client.post("/api/properties", json=property_payload).status_code == 422

    def test_rejects_unknown_property_status(self, client, property_payload):
        property_payload["property_status"] = "haunted"
        assert client.post("/api/properties", json=property_payload).status_code == 422

    def test_rejects_negative_money(self, client, property_payload):
        property_payload["listing_price"] = "-5000"
        assert client.post("/api/properties", json=property_payload).status_code == 422

    def test_rejects_absurd_year_built(self, client, property_payload):
        property_payload["year_built"] = 999
        assert client.post("/api/properties", json=property_payload).status_code == 422

    def test_rejects_unknown_fields(self, client, property_payload):
        """Unknown keys are refused rather than silently dropped."""
        property_payload["sneaky_field"] = "value"
        assert client.post("/api/properties", json=property_payload).status_code == 422

    def test_rejects_unknown_lead_type(self, client, created_property):
        response = client.post(
            "/api/leads",
            json={"property_id": created_property["id"], "lead_type": "psychic_hunch"},
        )
        assert response.status_code == 422


class TestAnalyzer:
    def test_analyze_returns_every_strategy(self, client, analysis_payload):
        body = client.post("/api/analyze", json=analysis_payload).json()
        assert set(body["strategies"]) == {
            "wholesale",
            "flip",
            "buy_hold",
            "brrrr",
            "seller_finance",
        }

    def test_analyze_recommends_and_explains(self, client, analysis_payload):
        body = client.post("/api/analyze", json=analysis_payload).json()
        assert body["recommended_strategy"] is not None
        assert body["rationale"]
        assert body["scoring"]["verdict"]

    def test_analyze_reports_confidence_and_risks(self, client, analysis_payload):
        body = client.post("/api/analyze", json=analysis_payload).json()
        assert body["overall_confidence"] in ("HIGH", "MEDIUM", "LOW")
        assert isinstance(body["scoring"]["risk_flags"], list)

    def test_money_is_returned_as_strings(self, client, analysis_payload):
        """Precision survives the wire; the UI never sees a float."""
        body = client.post("/api/analyze", json=analysis_payload).json()
        assert isinstance(body["strategies"]["flip"]["profit"], str)

    def test_changing_an_assumption_changes_the_result(self, client, analysis_payload):
        before = client.post("/api/analyze", json=analysis_payload).json()
        analysis_payload["assumptions"]["flip"] = {"rehab_contingency": "0.30"}
        after = client.post("/api/analyze", json=analysis_payload).json()
        assert Decimal(after["strategies"]["flip"]["profit"]) < Decimal(
            before["strategies"]["flip"]["profit"]
        )

    def test_analysis_works_with_almost_no_information(self, client):
        """A half-filled form still returns useful analysis."""
        body = client.post("/api/analyze", json={"purchase_price": "100000"}).json()
        assert body["strategies"]["flip"]["viable"] is False
        assert "arv" in body["strategies"]["flip"]["missing_inputs"]
        assert "arv" in body["missing_information"]

    def test_empty_request_does_not_error(self, client):
        response = client.post("/api/analyze", json={})
        assert response.status_code == 200
        assert response.json()["recommended_strategy"] is None

    def test_analyze_does_not_persist_anything(self, client, analysis_payload):
        client.post("/api/analyze", json=analysis_payload)
        assert client.get("/api/properties").json() == []

    def test_ai_analysis_is_absent_unless_requested(self, client, analysis_payload):
        assert client.post("/api/analyze", json=analysis_payload).json()["ai_analysis"] is None

    def test_ai_analysis_works_with_no_provider_configured(self, client, analysis_payload):
        """With no API key, the agents still produce real analysis."""
        analysis_payload["include_ai"] = True
        ai = client.post("/api/analyze", json=analysis_payload).json()["ai_analysis"]
        assert ai["underwriting"]["deterministic"] is True
        assert ai["underwriting"]["provider"] == "null"
        assert ai["underwriting"]["challenges"]
        assert ai["strategist"]["summary"]

    def test_ai_output_is_labelled_as_interpretation(self, client, analysis_payload):
        analysis_payload["include_ai"] = True
        ai = client.post("/api/analyze", json=analysis_payload).json()["ai_analysis"]
        assert "not by a language model" in ai["research"]["disclaimer"]

    def test_research_claims_are_labelled_fact_estimate_or_unknown(
        self, client, analysis_payload
    ):
        analysis_payload["include_ai"] = True
        claims = client.post("/api/analyze", json=analysis_payload).json()["ai_analysis"][
            "research"
        ]["claims"]
        assert claims
        for claim in claims:
            assert claim["assertion"] in ("FACT", "ESTIMATE", "INFERENCE", "UNKNOWN")


class TestSavedAnalyses:
    def test_save_and_reopen(self, client, created_property, analysis_payload):
        saved = client.post(
            f"/api/properties/{created_property['id']}/analyses",
            json={**analysis_payload, "name": "Initial underwriting"},
        )
        assert saved.status_code == 201, saved.text
        analysis_id = saved.json()["id"]

        reopened = client.get(f"/api/analyses/{analysis_id}").json()
        assert reopened["name"] == "Initial underwriting"
        assert reopened["recommended_strategy"] == saved.json()["recommended_strategy"]
        assert reopened["strategies"] == saved.json()["strategies"]

    def test_reopening_returns_stored_numbers_not_a_recomputation(
        self, client, created_property, analysis_payload
    ):
        """A saved analysis must read the same later, whatever defaults change."""
        saved = client.post(
            f"/api/properties/{created_property['id']}/analyses", json=analysis_payload
        ).json()
        first = client.get(f"/api/analyses/{saved['id']}").json()
        second = client.get(f"/api/analyses/{saved['id']}").json()
        assert first == second
        assert first["strategies"] == saved["strategies"]

    def test_list_analyses_for_a_property(self, client, created_property, analysis_payload):
        for _ in range(2):
            client.post(
                f"/api/properties/{created_property['id']}/analyses", json=analysis_payload
            )
        assert len(client.get(f"/api/properties/{created_property['id']}/analyses").json()) == 2

    def test_property_summary_carries_the_latest_verdict(
        self, client, created_property, analysis_payload
    ):
        client.post(
            f"/api/properties/{created_property['id']}/analyses", json=analysis_payload
        )
        summary = client.get("/api/properties").json()[0]
        assert summary["verdict"] is not None
        assert summary["latest_analysis_id"] is not None

    def test_update_re_underwrites(self, client, created_property, analysis_payload):
        saved = client.post(
            f"/api/properties/{created_property['id']}/analyses", json=analysis_payload
        ).json()
        updated = client.put(
            f"/api/analyses/{saved['id']}",
            json={
                **analysis_payload,
                "purchase_price": "120000",
                "change_reason": "Seller countered lower",
            },
        ).json()
        assert Decimal(updated["strategies"]["flip"]["profit"]) > Decimal(
            saved["strategies"]["flip"]["profit"]
        )

    def test_delete(self, client, created_property, analysis_payload):
        saved = client.post(
            f"/api/properties/{created_property['id']}/analyses", json=analysis_payload
        ).json()
        assert client.delete(f"/api/analyses/{saved['id']}").status_code == 204
        assert client.get(f"/api/analyses/{saved['id']}").status_code == 404

    def test_ai_can_be_generated_for_a_saved_analysis(
        self, client, created_property, analysis_payload
    ):
        saved = client.post(
            f"/api/properties/{created_property['id']}/analyses", json=analysis_payload
        ).json()
        body = client.post(f"/api/analyses/{saved['id']}/ai").json()
        assert body["ai_analysis"]["strategist"]["summary"]


class TestAuditTrail:
    def test_initial_save_records_the_starting_assumptions(
        self, client, created_property, analysis_payload
    ):
        saved = client.post(
            f"/api/properties/{created_property['id']}/analyses", json=analysis_payload
        ).json()
        trail = client.get(f"/api/analyses/{saved['id']}/audit").json()
        assert trail
        assert any(e["field_path"] == "arv" for e in trail)

    def test_changing_arv_is_recorded_with_both_values(
        self, client, created_property, analysis_payload
    ):
        saved = client.post(
            f"/api/properties/{created_property['id']}/analyses", json=analysis_payload
        ).json()
        client.put(
            f"/api/analyses/{saved['id']}",
            json={
                **analysis_payload,
                "arv": "280000",
                "change_reason": "Two newer comps closed higher",
            },
        )
        trail = client.get(f"/api/analyses/{saved['id']}/audit").json()
        arv_change = next(
            e for e in trail if e["field_path"] == "arv" and e["previous_value"] == "250000"
        )
        assert arv_change["new_value"] == "280000"
        assert arv_change["reason"] == "Two newer comps closed higher"
        assert arv_change["changed_by"] is not None
        assert arv_change["changed_at"] is not None

    def test_changing_an_operating_expense_is_recorded(
        self, client, created_property, analysis_payload
    ):
        saved = client.post(
            f"/api/properties/{created_property['id']}/analyses", json=analysis_payload
        ).json()
        analysis_payload["assumptions"]["rental"]["vacancy_percent"] = "0.10"
        client.put(f"/api/analyses/{saved['id']}", json=analysis_payload)
        trail = client.get(f"/api/analyses/{saved['id']}/audit").json()
        assert any(e["field_path"] == "assumptions.rental.vacancy_percent" for e in trail)

    def test_an_unchanged_resave_records_nothing_new(
        self, client, created_property, analysis_payload
    ):
        """Re-saving identical numbers must not fill the trail with noise."""
        saved = client.post(
            f"/api/properties/{created_property['id']}/analyses", json=analysis_payload
        ).json()
        before = len(client.get(f"/api/analyses/{saved['id']}/audit").json())
        client.put(f"/api/analyses/{saved['id']}", json=analysis_payload)
        after = len(client.get(f"/api/analyses/{saved['id']}/audit").json())
        assert after == before


class TestSettings:
    def test_defaults_are_returned_and_labelled_provisional(self, client):
        body = client.get("/api/settings").json()
        assert body["default_assumptions"]["flip"]["minimum_net_profit"] == "30000"
        assert "Provisional" in body["provisional_defaults_note"]

    def test_saving_a_buy_box_changes_future_analyses(self, client, analysis_payload):
        client.put(
            "/api/settings",
            json={"default_assumptions": {"flip": {"minimum_net_profit": "60000"}}},
        )
        body = client.post("/api/analyze", json=analysis_payload).json()
        criteria = {
            c["name"]: c for c in body["strategies"]["flip"]["criteria"]
        }
        assert criteria["minimum_net_profit"]["target"] == "60000"

    def test_deal_overrides_beat_saved_defaults(self, client, analysis_payload):
        client.put(
            "/api/settings",
            json={"default_assumptions": {"flip": {"minimum_net_profit": "60000"}}},
        )
        analysis_payload["assumptions"]["flip"] = {"minimum_net_profit": "10000"}
        body = client.post("/api/analyze", json=analysis_payload).json()
        criteria = {c["name"]: c for c in body["strategies"]["flip"]["criteria"]}
        assert criteria["minimum_net_profit"]["target"] == "10000"

    def test_partial_buy_box_keeps_other_defaults(self, client):
        client.put(
            "/api/settings",
            json={"default_assumptions": {"flip": {"minimum_net_profit": "60000"}}},
        )
        body = client.get("/api/settings").json()
        assert body["default_assumptions"]["flip"]["minimum_net_profit"] == "60000"
        assert body["default_assumptions"]["rental"]["vacancy_percent"] == "0.05"

    def test_reset_restores_provisional_defaults(self, client):
        client.put(
            "/api/settings",
            json={"default_assumptions": {"flip": {"minimum_net_profit": "60000"}}},
        )
        body = client.post("/api/settings/reset").json()
        assert body["default_assumptions"]["flip"]["minimum_net_profit"] == "30000"


class TestLeads:
    def test_create_and_list(self, client, created_property):
        created = client.post(
            "/api/leads",
            json={
                "property_id": created_property["id"],
                "lead_type": "absentee",
                "source": "county record",
            },
        )
        assert created.status_code == 201
        assert len(client.get("/api/leads").json()) == 1

    def test_filter_by_type(self, client, created_property):
        client.post(
            "/api/leads",
            json={"property_id": created_property["id"], "lead_type": "vacant"},
        )
        assert len(client.get("/api/leads?lead_type=vacant").json()) == 1
        assert len(client.get("/api/leads?lead_type=probate").json()) == 0

    def test_update_status(self, client, created_property):
        lead = client.post(
            "/api/leads",
            json={"property_id": created_property["id"], "lead_type": "FSBO"},
        ).json()
        updated = client.patch(f"/api/leads/{lead['id']}", json={"status": "contacted"})
        assert updated.json()["status"] == "contacted"

    def test_cannot_attach_a_lead_to_an_unknown_property(self, client):
        response = client.post(
            "/api/leads", json={"property_id": str(uuid.uuid4()), "lead_type": "vacant"}
        )
        assert response.status_code == 404


class TestRelatedRecords:
    def test_comps(self, client, created_property):
        created = client.post(
            f"/api/properties/{created_property['id']}/comps",
            json={
                "address": "418 Magnolia Street",
                "sale_price": "248000",
                "similarity_score": "0.9",
            },
        )
        assert created.status_code == 201
        assert len(client.get(f"/api/properties/{created_property['id']}/comps").json()) == 1

    def test_offers(self, client, created_property):
        created = client.post(
            f"/api/properties/{created_property['id']}/offers",
            json={"offer_amount": "140000", "offer_type": "cash", "status": "draft"},
        )
        assert created.status_code == 201

    def test_communications(self, client, created_property):
        created = client.post(
            f"/api/properties/{created_property['id']}/communications",
            json={
                "communication_type": "call",
                "direction": "outbound",
                "outcome": "left voicemail",
            },
        )
        assert created.status_code == 201

    def test_rehab_project_reports_variance(self, client, created_property):
        created = client.post(
            f"/api/properties/{created_property['id']}/rehab-projects",
            json={"estimated_rehab": "45000", "actual_rehab": "52000"},
        ).json()
        assert created["variance"] == "7000.00"

    def test_owner_records_occupancy_without_inferring_motivation(
        self, client, created_property
    ):
        created = client.post(
            f"/api/properties/{created_property['id']}/owners",
            json={"owner_name": "Example Holdings LLC", "occupancy_indicator": "absentee"},
        )
        assert created.status_code == 201
        assert created.json()["occupancy_indicator"] == "absentee"


class TestEnrichment:
    def test_enrich_without_a_provider_is_a_clear_no_op(self, client, created_property):
        body = client.post(f"/api/properties/{created_property['id']}/enrich").json()
        assert body["provider"] == "none"
        assert body["imported"] == []
        assert "manually entered data" in body["detail"]


class TestDashboard:
    def test_empty_dashboard(self, client):
        body = client.get("/api/dashboard").json()
        assert body["property_count"] == 0
        assert body["top_opportunities"] == []

    def test_dashboard_counts_and_totals(self, client, created_property, analysis_payload):
        client.post(
            f"/api/properties/{created_property['id']}/analyses", json=analysis_payload
        )
        body = client.get("/api/dashboard").json()
        assert body["property_count"] == 1
        assert body["analyzed_count"] == 1
        assert body["pipeline"]

    def test_only_the_latest_analysis_per_property_is_counted(
        self, client, created_property, analysis_payload
    ):
        """Re-analysing a property must not double-count it in the totals."""
        for _ in range(3):
            client.post(
                f"/api/properties/{created_property['id']}/analyses", json=analysis_payload
            )
        assert client.get("/api/dashboard").json()["analyzed_count"] == 1

    def test_recent_activity_is_recorded(self, client, created_property):
        activity = client.get("/api/dashboard").json()["recent_activity"]
        assert any(a["action"] == "property.created" for a in activity)
