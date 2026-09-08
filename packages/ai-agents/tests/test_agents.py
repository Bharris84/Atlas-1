"""AI agents.

Two properties matter more than anything else here:

1. The agents never produce a number.
2. Nothing identifying a person is sent to a model.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from atlas_financial_engine import (
    Assumptions,
    DealInputs,
    Evidence,
    HoldingCosts,
    PropertyFacts,
    RehabBasis,
    RentBasis,
    RentalAssumptions,
    ValueBasis,
    analyze_all_strategies,
)
from atlas_financial_engine.money import D
from atlas_ai_agents import (
    AIProvider,
    AIProviderError,
    NullProvider,
    build_context,
    extract_json,
    get_ai_provider,
    research_property,
    run_all_agents,
    strategise,
    underwrite,
)
from atlas_ai_agents.providers import Completion


@pytest.fixture
def deal() -> DealInputs:
    return DealInputs(
        purchase_price=D("150000"),
        arv=D("250000"),
        rehab=D("45000"),
        monthly_rent=D("1800"),
        assumptions=Assumptions(
            holding=HoldingCosts(annual_taxes=D("2400"), annual_insurance=D("1800")),
            rental=RentalAssumptions(annual_taxes=D("2400"), annual_insurance=D("1800")),
        ),
        property_facts=PropertyFacts(
            address="412 Magnolia Street",
            city="Chattanooga",
            state="TN",
            zip_code="37402",
            property_type="single_family",
            bedrooms=D("3"),
            year_built=1998,
        ),
        evidence=Evidence(
            arv_basis=ValueBasis.AUTOMATED_VALUATION,
            comp_count=2,
            rehab_basis=RehabBasis.USER_ENTERED,
            rent_basis=RentBasis.AUTOMATED_ESTIMATE,
        ),
    )


@pytest.fixture
def comparison(deal):
    return analyze_all_strategies(deal)


class _ScriptedProvider(AIProvider):
    """A model that returns whatever it is told to."""

    name = "scripted"

    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.prompts = []

    @property
    def is_configured(self) -> bool:
        return True

    def complete(self, system, prompt, max_tokens=1500, temperature=0.2) -> Completion:
        self.prompts.append({"system": system, "prompt": prompt})
        return Completion(text=self.payload, provider=self.name, model="scripted-1")


class _BrokenProvider(AIProvider):
    name = "broken"

    @property
    def is_configured(self) -> bool:
        return True

    def complete(self, system, prompt, max_tokens=1500, temperature=0.2) -> Completion:
        raise AIProviderError("upstream is down")


class TestProviderSelection:
    def test_no_provider_configured_yields_the_null_provider(self):
        assert get_ai_provider(None).name == "null"

    def test_unknown_provider_falls_back_rather_than_raising(self):
        assert get_ai_provider("some-model-vendor").name == "null"

    def test_anthropic_without_a_key_falls_back(self):
        assert get_ai_provider("anthropic", api_key=None).name == "null"

    def test_openai_without_a_key_falls_back(self):
        assert get_ai_provider("openai", api_key=None).name == "null"

    def test_provider_is_swappable_without_touching_the_agents(self, deal, comparison):
        """The point of the abstraction: same agent, different vendor."""
        scripted = _ScriptedProvider(json.dumps({"summary": "From a model."}))
        assert underwrite(deal, comparison, scripted).provider == "scripted"
        assert underwrite(deal, comparison, NullProvider()).provider == "null"


class TestWorksWithoutAModel:
    def test_all_agents_produce_output_with_no_provider(self, deal, comparison):
        output = run_all_agents(deal, comparison)
        for agent in ("research", "underwriting", "strategist"):
            assert output[agent]["summary"]
            assert output[agent]["deterministic"] is True

    def test_deterministic_underwriting_still_challenges_assumptions(
        self, deal, comparison
    ):
        result = underwrite(deal, comparison)
        assert result.challenges
        assert any("ARV" in c for c in result.challenges)

    def test_deterministic_output_is_reproducible(self, deal, comparison):
        first = underwrite(deal, comparison).challenges
        second = underwrite(deal, comparison).challenges
        assert first == second

    def test_a_failing_model_degrades_to_deterministic_output(self, deal, comparison):
        """Losing narration is acceptable. Losing the analysis is not."""
        result = underwrite(deal, comparison, _BrokenProvider())
        assert result.deterministic is True
        assert result.provider == "null"
        assert result.challenges

    def test_unparseable_model_output_degrades_to_deterministic(self, deal, comparison):
        result = underwrite(deal, comparison, _ScriptedProvider("I'm afraid I can't."))
        assert result.deterministic is True
        assert result.challenges


class TestModelOutputIsUsedWhenAvailable:
    def test_model_narrative_is_returned(self, deal, comparison):
        provider = _ScriptedProvider(
            json.dumps(
                {
                    "summary": "Marginal flip, decent wholesale.",
                    "narrative": ["The spread is thin."],
                    "challenges": ["The ARV is an AVM figure."],
                }
            )
        )
        result = underwrite(deal, comparison, provider)
        assert result.deterministic is False
        assert result.summary == "Marginal flip, decent wholesale."
        assert result.narrative == ["The spread is thin."]

    def test_json_is_extracted_from_a_fenced_response(self, deal, comparison):
        provider = _ScriptedProvider('```json\n{"summary": "Fenced."}\n```')
        assert underwrite(deal, comparison, provider).summary == "Fenced."

    def test_model_output_is_length_bounded(self, deal, comparison):
        provider = _ScriptedProvider(json.dumps({"summary": "x" * 5000}))
        assert len(underwrite(deal, comparison, provider).summary) <= 600

    def test_non_string_list_items_are_discarded(self, deal, comparison):
        provider = _ScriptedProvider(
            json.dumps({"summary": "ok", "challenges": [{"text": "kept"}, 42, None]})
        )
        assert underwrite(deal, comparison, provider).challenges == ["kept"]


class TestPrivacy:
    def test_the_street_address_is_not_sent_to_a_model(self, deal, comparison):
        context = build_context(deal, comparison)
        assert "412 Magnolia" not in json.dumps(context)
        assert context["property"]["location"]["city"] == "Chattanooga"

    def test_no_owner_information_reaches_the_context(self, deal, comparison):
        """A model needs the market and the numbers. It does not need a name."""
        context = json.dumps(build_context(deal, comparison)).lower()
        for forbidden in ("owner_name", "mailing", "contact", "phone", "email"):
            assert forbidden not in context

    def test_the_prompt_sent_to_a_model_contains_no_street_address(
        self, deal, comparison
    ):
        provider = _ScriptedProvider(json.dumps({"summary": "ok"}))
        underwrite(deal, comparison, provider)
        assert "412 Magnolia" not in provider.prompts[0]["prompt"]

    def test_context_carries_computed_results_not_raw_inputs_alone(
        self, deal, comparison
    ):
        context = build_context(deal, comparison)
        assert context["strategies"]["flip"]["profit"] is not None
        assert context["recommended_strategy"] is not None


class TestTheAiNeverCalculates:
    def test_the_system_prompt_forbids_arithmetic(self, deal, comparison):
        provider = _ScriptedProvider(json.dumps({"summary": "ok"}))
        underwrite(deal, comparison, provider)
        system = provider.prompts[0]["system"]
        assert "must NOT perform arithmetic" in system
        assert "deterministic engine" in system

    def test_every_figure_in_output_comes_from_the_engine(self, deal, comparison):
        """Even if a model invents a number, the numbers Atlas shows are engine
        numbers: the model's contribution is confined to prose fields."""
        provider = _ScriptedProvider(
            json.dumps({"summary": "Profit is $999,999,999.", "narrative": ["Nonsense."]})
        )
        result = underwrite(deal, comparison, provider).to_dict()
        # The model's text is quarantined in narrative/summary and labelled.
        assert "not by a language model" in result["disclaimer"]
        assert result["claims"] == []

    def test_research_claims_are_built_deterministically(self, deal, comparison):
        provider = _ScriptedProvider(json.dumps({"summary": "ok", "claims": ["fake"]}))
        claims = research_property(deal, comparison, provider).claims
        # Claims come from the engine's evidence, never from the model.
        arv_claim = next(c for c in claims if c.label == "After-repair value")
        assert arv_claim.value == "250000"
        assert "automated_valuation" in arv_claim.source


class TestLabelling:
    def test_claims_carry_fact_estimate_or_unknown(self, deal, comparison):
        for claim in research_property(deal, comparison).claims:
            assert claim.assertion.value in ("FACT", "ESTIMATE", "INFERENCE", "UNKNOWN")

    def test_a_missing_value_is_labelled_unknown_not_zero(self, deal, comparison):
        stripped = DealInputs(
            purchase_price=D("150000"), assumptions=deal.assumptions
        )
        claims = research_property(stripped, analyze_all_strategies(stripped)).claims
        arv = next(c for c in claims if c.label == "After-repair value")
        assert arv.value is None
        assert arv.assertion.value == "UNKNOWN"

    def test_sources_are_cited(self, deal, comparison):
        sources = research_property(deal, comparison).sources
        assert any("ARV basis" in s for s in sources)

    def test_missing_information_is_described_in_plain_language(self, deal, comparison):
        stripped = DealInputs(assumptions=deal.assumptions)
        result = research_property(stripped, analyze_all_strategies(stripped))
        assert any("After-repair value" in m for m in result.missing_information)


class TestStrategist:
    def test_recommends_and_explains(self, deal, comparison):
        result = strategise(deal, comparison)
        assert result.summary
        assert result.narrative

    def test_flags_low_confidence_in_the_recommendation(self, deal, comparison):
        result = strategise(deal, comparison)
        assert any("confidence" in q.lower() for q in result.questions)

    def test_handles_a_deal_with_no_viable_strategy(self, deal):
        empty = DealInputs(assumptions=deal.assumptions)
        result = strategise(empty, analyze_all_strategies(empty))
        assert "No strategy" in result.summary


class TestJsonExtraction:
    def test_plain_json(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_json_surrounded_by_prose(self):
        assert extract_json('Here you go:\n{"a": 1}\nHope that helps.') == {"a": 1}

    def test_invalid_json_returns_none(self):
        assert extract_json("{not json}") is None

    def test_empty_returns_none(self):
        assert extract_json("") is None

    def test_a_json_array_is_rejected(self):
        assert extract_json("[1, 2, 3]") is None


class TestSerialization:
    def test_output_is_json_serialisable(self, deal, comparison):
        payload = run_all_agents(deal, comparison)
        assert json.loads(json.dumps(payload))["research"]["agent"] == "research"
