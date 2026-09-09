"""Investor profile.

The profile describes the INVESTOR, not the deal. These tests protect that
separation and the rule that an unstated figure is unknown, never zero.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from atlas_financial_engine import (
    Assumptions,
    CapitalEfficiencyPreference,
    DealInputs,
    InvestorProfile,
    RiskTolerance,
    Strategy,
)
from atlas_financial_engine.money import D


class TestDefaults:
    def test_an_empty_profile_states_nothing(self):
        # Absence of a figure is not a figure. An investor who has not said what
        # capital they have does not have zero capital.
        profile = InvestorProfile()
        assert profile.is_stated is False
        assert profile.available_capital is None
        assert profile.capital_ceiling is None

    def test_a_profile_with_any_figure_is_stated(self):
        assert InvestorProfile(available_capital=D("50000")).is_stated is True

    def test_stating_only_preferred_strategies_counts(self):
        assert InvestorProfile(preferred_strategies=[Strategy.WHOLESALE]).is_stated is True

    def test_default_risk_tolerance_is_moderate(self):
        assert InvestorProfile().risk_tolerance == RiskTolerance.MODERATE

    def test_default_capital_preference_is_balanced(self):
        assert (
            InvestorProfile().capital_efficiency_preference
            == CapitalEfficiencyPreference.BALANCED
        )


class TestCapitalCeiling:
    def test_the_lower_of_the_two_limits_binds(self):
        """Willingness to commit usually binds before total capital does."""
        profile = InvestorProfile(
            available_capital=D("100000"), max_capital_deployment=D("35000")
        )
        assert profile.capital_ceiling == D("35000")

    def test_available_capital_binds_when_it_is_lower(self):
        profile = InvestorProfile(
            available_capital=D("20000"), max_capital_deployment=D("35000")
        )
        assert profile.capital_ceiling == D("20000")

    def test_either_limit_alone_is_the_ceiling(self):
        assert InvestorProfile(available_capital=D("40000")).capital_ceiling == D("40000")
        assert (
            InvestorProfile(max_capital_deployment=D("15000")).capital_ceiling == D("15000")
        )

    def test_no_stated_limit_means_no_ceiling_not_a_zero_ceiling(self):
        assert InvestorProfile().capital_ceiling is None


class TestStrategyPreference:
    def test_no_stated_preference_accepts_everything(self):
        """Silence means "no preference", not "nothing is acceptable"."""
        profile = InvestorProfile()
        assert all(profile.prefers(s) for s in Strategy)

    def test_a_stated_preference_excludes_the_rest(self):
        profile = InvestorProfile(
            preferred_strategies=[Strategy.WHOLESALE, Strategy.FLIP]
        )
        assert profile.prefers(Strategy.WHOLESALE) is True
        assert profile.prefers(Strategy.BRRRR) is False


class TestRiskTolerance:
    def test_tolerance_is_ordered(self):
        assert (
            RiskTolerance.CONSERVATIVE.rank
            < RiskTolerance.MODERATE.rank
            < RiskTolerance.AGGRESSIVE.rank
        )


class TestSerialization:
    def test_round_trips(self):
        profile = InvestorProfile(
            name="Test investor",
            available_capital=D("75000"),
            max_capital_deployment=D("40000"),
            preferred_minimum_cash_flow=D("350"),
            minimum_roi=D("0.25"),
            max_cash_left_in_deal=D("15000"),
            minimum_wholesale_assignment=D("12000"),
            risk_tolerance=RiskTolerance.CONSERVATIVE,
            capital_efficiency_preference=CapitalEfficiencyPreference.MAXIMIZE_VELOCITY,
            preferred_strategies=[Strategy.WHOLESALE],
        )
        restored = InvestorProfile.from_dict(profile.to_dict())
        assert restored == profile

    def test_money_serialises_as_a_string(self):
        payload = InvestorProfile(available_capital=D("50000")).to_dict()
        assert payload["available_capital"] == "50000"

    def test_partial_input_keeps_defaults(self):
        restored = InvestorProfile.from_dict({"available_capital": "60000"})
        assert restored.available_capital == D("60000")
        assert restored.risk_tolerance == RiskTolerance.MODERATE
        assert restored.minimum_roi is None

    def test_unknown_keys_are_ignored(self):
        assert InvestorProfile.from_dict({"a_field_from_the_future": 1}) == InvestorProfile()

    def test_none_yields_an_empty_profile(self):
        assert InvestorProfile.from_dict(None) == InvestorProfile()

    def test_explicit_null_clears_a_value(self):
        assert InvestorProfile.from_dict({"available_capital": None}).available_capital is None

    def test_json_serialisable(self):
        import json

        payload = InvestorProfile(available_capital=D("50000")).to_dict()
        assert json.loads(json.dumps(payload))["risk_tolerance"] == "moderate"


class TestIntegrationWithDealInputs:
    def test_deal_inputs_carry_a_profile(self):
        inputs = DealInputs(
            purchase_price=D("100000"),
            investor_profile=InvestorProfile(available_capital=D("50000")),
        )
        assert inputs.investor_profile.available_capital == D("50000")

    def test_deal_inputs_default_to_an_unstated_profile(self):
        assert DealInputs().investor_profile.is_stated is False

    def test_the_profile_survives_a_deal_round_trip(self):
        inputs = DealInputs(
            purchase_price=D("100000"),
            investor_profile=InvestorProfile(
                available_capital=D("50000"), minimum_roi=D("0.3")
            ),
        )
        restored = DealInputs.from_dict(inputs.to_dict())
        assert restored.investor_profile.available_capital == D("50000")
        assert restored.investor_profile.minimum_roi == D("0.3")

    def test_the_profile_does_not_change_the_underwriting(self):
        """The profile constrains what the investor can DO, not what a deal IS.

        Wiring it into the deal maths is a later decision; until then the same
        property must underwrite identically for every investor.
        """
        from atlas_financial_engine import analyze_all_strategies

        base = DealInputs(
            purchase_price=D("150000"),
            arv=D("250000"),
            rehab=D("45000"),
            monthly_rent=D("1800"),
        )
        rich = base.__class__(
            **{
                **base.__dict__,
                "investor_profile": InvestorProfile(available_capital=D("5000000")),
            }
        )
        poor = base.__class__(
            **{
                **base.__dict__,
                "investor_profile": InvestorProfile(available_capital=D("5000")),
            }
        )
        assert (
            analyze_all_strategies(rich).results[Strategy.FLIP].profit
            == analyze_all_strategies(poor).results[Strategy.FLIP].profit
        )


class TestNoDefaultProfileShips:
    """Atlas must ship no populated investor profile.

    A constant carrying example capital figures is a liability: anyone reading
    the codebase could mistake an illustration for the operator's real
    position, and an underwriting tool that appears to know your balance sheet
    when it does not is worse than one that admits it does not.
    """

    def test_no_populated_profile_constant_is_exported(self):
        import atlas_financial_engine as engine

        for name in dir(engine):
            value = getattr(engine, name)
            if isinstance(value, InvestorProfile):
                assert not value.is_stated, (
                    f"{name} ships populated capital figures; Atlas must not "
                    "imply knowledge of the investor's position"
                )

    def test_the_default_profile_states_nothing(self):
        assert InvestorProfile().is_stated is False

    def test_the_provisional_note_still_exists_for_user_entered_profiles(self):
        from atlas_financial_engine import PROVISIONAL_PROFILE_NOTE

        assert "Provisional" in PROVISIONAL_PROFILE_NOTE
