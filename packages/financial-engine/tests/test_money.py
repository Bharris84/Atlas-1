"""Money primitives. Everything downstream inherits any error made here."""

from __future__ import annotations

from decimal import Decimal

import pytest

from atlas_financial_engine.money import (
    D,
    MoneyError,
    money,
    non_negative,
    pct_of,
    ratio,
    safe_div,
)


class TestD:
    def test_float_does_not_leak_binary_expansion(self):
        assert D(0.1) == Decimal("0.1")
        assert D(0.1) + D(0.2) == Decimal("0.3")

    def test_parses_formatted_currency(self):
        assert D("$1,250,000.50") == Decimal("1250000.50")

    def test_parses_percentage_strings(self):
        assert D("7.5%") == Decimal("0.075")

    def test_rejects_bool(self):
        # bool is an int subclass; accepting it silently would let a flag be
        # summed as money.
        with pytest.raises(MoneyError):
            D(True)

    def test_rejects_garbage(self):
        with pytest.raises(MoneyError):
            D("not a number")

    def test_rejects_unsupported_type(self):
        with pytest.raises(MoneyError):
            D([1])


class TestRounding:
    def test_money_rounds_half_up(self):
        assert money("2.005") == Decimal("2.01")
        assert money("2.004") == Decimal("2.00")

    def test_money_rounds_half_up_on_negatives(self):
        assert money("-2.005") == Decimal("-2.01")

    def test_ratio_is_four_places(self):
        assert ratio("0.123456") == Decimal("0.1235")


class TestSafeDiv:
    def test_zero_denominator_is_none_not_zero(self):
        # "Undefined" and "zero percent" are different claims about a deal.
        assert safe_div(100, 0) is None

    def test_normal_division_is_exact(self):
        assert safe_div(1, 4) == Decimal("0.25")


class TestHelpers:
    def test_pct_of(self):
        assert pct_of(250000, "0.06") == Decimal("15000.00")

    def test_non_negative_floors_at_zero(self):
        assert non_negative("-5") == Decimal("0")
        assert non_negative("5") == Decimal("5")
