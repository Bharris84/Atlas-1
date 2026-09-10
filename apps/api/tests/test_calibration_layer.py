"""API surface for the calibration phase: investor profile and capital efficiency."""

from __future__ import annotations

from decimal import Decimal

import pytest


class TestInvestorProfileSettings:
    def test_an_unset_profile_returns_empty_values_not_zeros(self, client):
        profile = client.get("/api/settings").json()["investor_profile"]
        # Nothing stated means nothing known — never a zero that would read as
        # "this investor has no money".
        assert profile["available_capital"] is None
        assert profile["minimum_roi"] is None

    def test_defaults_that_do_exist_are_returned(self, client):
        profile = client.get("/api/settings").json()["investor_profile"]
        assert profile["risk_tolerance"] == "moderate"
        assert profile["capital_efficiency_preference"] == "balanced"

    def test_the_profile_is_labelled_provisional(self, client):
        body = client.get("/api/settings").json()
        assert "Provisional investor profile" in body["provisional_profile_note"]

    def test_saving_and_reading_a_profile(self, client):
        saved = client.put(
            "/api/settings",
            json={
                "investor_profile": {
                    "available_capital": "75000",
                    "max_capital_deployment": "40000",
                    "preferred_minimum_cash_flow": "400",
                    "minimum_roi": "0.25",
                    "max_cash_left_in_deal": "15000",
                    "minimum_wholesale_assignment": "12000",
                    "risk_tolerance": "conservative",
                    "capital_efficiency_preference": "maximize_velocity",
                    "preferred_strategies": ["wholesale", "flip"],
                }
            },
        )
        assert saved.status_code == 200, saved.text
        profile = saved.json()["investor_profile"]
        assert profile["available_capital"] == "75000"
        assert profile["risk_tolerance"] == "conservative"
        assert profile["preferred_strategies"] == ["wholesale", "flip"]

        assert client.get("/api/settings").json()["investor_profile"] == profile

    def test_the_profile_is_separate_from_the_buy_box(self, client):
        """Changing one must not disturb the other."""
        client.put(
            "/api/settings",
            json={"default_assumptions": {"flip": {"minimum_net_profit": "60000"}}},
        )
        client.put("/api/settings", json={"investor_profile": {"available_capital": "80000"}})
        body = client.get("/api/settings").json()
        assert body["default_assumptions"]["flip"]["minimum_net_profit"] == "60000"
        assert body["investor_profile"]["available_capital"] == "80000"

    def test_an_invalid_profile_is_rejected(self, client):
        response = client.put(
            "/api/settings", json={"investor_profile": {"risk_tolerance": "reckless"}}
        )
        assert response.status_code == 422

    def test_reset_clears_the_profile_too(self, client):
        client.put("/api/settings", json={"investor_profile": {"available_capital": "80000"}})
        body = client.post("/api/settings/reset").json()
        assert body["investor_profile"]["available_capital"] is None


class TestCapitalEfficiencyInAnalysis:
    def test_every_strategy_gets_a_metric(self, client, analysis_payload):
        body = client.post("/api/analyze", json=analysis_payload).json()
        assert set(body["capital_efficiency"]) == set(body["strategies"])

    def test_the_metric_publishes_its_inputs_and_formula(self, client, analysis_payload):
        """Transparency: a user must be able to recompute this by hand."""
        flip = client.post("/api/analyze", json=analysis_payload).json()[
            "capital_efficiency"
        ]["flip"]
        assert flip["formula"]
        assert flip["inputs"]["capital_deployed"]
        assert flip["inputs"]["profit"]
        assert flip["inputs"]["target_return"]
        # Where the target came from is stated precisely rather than as a
        # single boolean.
        assert flip["inputs"]["target_return_source"] in (
            "investor profile",
            "deal assumptions",
            "Atlas default",
        )

    def test_the_arithmetic_reproduces_from_the_published_inputs(
        self, client, analysis_payload
    ):
        flip = client.post("/api/analyze", json=analysis_payload).json()[
            "capital_efficiency"
        ]["flip"]
        profit = Decimal(flip["inputs"]["profit"])
        capital = Decimal(flip["inputs"]["capital_deployed"])
        months = Decimal(flip["inputs"]["horizon_months"])
        by_hand = (profit / capital) * (12 / months)
        # Published to 4dp, which is the precision a user checking this on a
        # calculator would arrive at.
        assert abs(Decimal(flip["annualized_return_on_capital"]) - by_hand) < Decimal(
            "0.0001"
        )

    def test_it_does_not_change_the_deal_score(self, client, analysis_payload):
        """Capital efficiency drives the strategy RANKING but not the deal
        score, which remains a separate seven-category rubric."""
        body = client.post("/api/analyze", json=analysis_payload).json()
        assert body["scoring"]["score"] is not None
        assert body["recommended_strategy"] is not None
        # The ranking components remain the seven originals.
        components = body["ranking"][0]["components"]
        assert set(components) == {
            "profit",
            "capital_efficiency",
            "roi",
            "cash_flow",
            "equity_creation",
            "time_to_liquidity",
            "risk",
        }

    def test_affordability_is_unknown_without_a_profile(self, client, analysis_payload):
        flip = client.post("/api/analyze", json=analysis_payload).json()[
            "capital_efficiency"
        ]["flip"]
        assert flip["within_capital_limit"] is None
        assert flip["share_of_available_capital"] is None

    def test_a_saved_profile_makes_affordability_answerable(
        self, client, analysis_payload
    ):
        client.put(
            "/api/settings",
            json={"investor_profile": {"available_capital": "20000", "minimum_roi": "0.2"}},
        )
        flip = client.post("/api/analyze", json=analysis_payload).json()[
            "capital_efficiency"
        ]["flip"]
        # The baseline flip needs more than $20,000 of cash.
        assert flip["within_capital_limit"] is False
        assert flip["share_of_available_capital"] is not None
        assert any("funding constraint" in n for n in flip["notes"])

    def test_a_per_analysis_profile_overrides_the_saved_one(
        self, client, analysis_payload
    ):
        client.put("/api/settings", json={"investor_profile": {"available_capital": "20000"}})
        body = client.post(
            "/api/analyze",
            json={**analysis_payload, "investor_profile": {"available_capital": "500000"}},
        ).json()
        assert body["capital_efficiency"]["flip"]["within_capital_limit"] is True

    def test_the_metric_survives_saving_and_reopening(
        self, client, created_property, analysis_payload
    ):
        saved = client.post(
            f"/api/properties/{created_property['id']}/analyses", json=analysis_payload
        ).json()
        assert saved["capital_efficiency"]["flip"]["formula"]
        reopened = client.get(f"/api/analyses/{saved['id']}").json()
        assert reopened["capital_efficiency"] == saved["capital_efficiency"]

    def test_the_investor_profile_is_recorded_with_the_saved_analysis(
        self, client, created_property, analysis_payload
    ):
        """An analysis must reproduce exactly, which means recording who it was
        underwritten for."""
        client.put("/api/settings", json={"investor_profile": {"available_capital": "60000"}})
        saved = client.post(
            f"/api/properties/{created_property['id']}/analyses", json=analysis_payload
        ).json()
        assert saved["inputs"]["investor_profile"]["available_capital"] == "60000"
