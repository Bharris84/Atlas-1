"""Loan mathematics, checked against known-good textbook values."""

from __future__ import annotations

from decimal import Decimal

import pytest

from atlas_financial_engine.loans import (
    amortization_schedule,
    dscr,
    monthly_payment,
    payment_factor,
    remaining_balance,
    total_interest_paid,
)
from atlas_financial_engine.money import D


class TestMonthlyPayment:
    def test_known_amortizing_payment(self):
        # $200,000 at 7.00% over 30 years = $1,330.60/mo (standard reference).
        assert monthly_payment(200000, "0.07", 30) == Decimal("1330.60")

    def test_known_amortizing_payment_second_case(self):
        # $100,000 at 6.00% over 30 years = $599.55/mo.
        assert monthly_payment(100000, "0.06", 30) == Decimal("599.55")

    def test_interest_only_payment_is_principal_times_monthly_rate(self):
        assert monthly_payment(150000, "0.12", 30, interest_only=True) == Decimal("1500.00")

    def test_zero_interest_amortizes_evenly(self):
        assert monthly_payment(120000, "0", 10) == Decimal("1000.00")

    def test_zero_principal_pays_nothing(self):
        assert monthly_payment(0, "0.07", 30) == Decimal("0")

    def test_negative_principal_pays_nothing(self):
        assert monthly_payment(-5000, "0.07", 30) == Decimal("0")

    def test_extreme_rate_does_not_explode(self):
        # A 35% hard-money-gone-wrong rate: payment approaches interest-only.
        payment = monthly_payment(100000, "0.35", 30)
        interest_only = monthly_payment(100000, "0.35", 30, interest_only=True)
        assert payment > interest_only
        assert payment < interest_only * D("1.01")

    def test_invalid_amortization_term_raises(self):
        with pytest.raises(ValueError):
            payment_factor("0.07", 0)


class TestRemainingBalance:
    def test_balance_after_five_years(self):
        # $200,000 at 7% / 30yr has ~$188,263 left after 60 payments.
        balance = remaining_balance(200000, "0.07", 30, 60)
        assert Decimal("188200") < balance < Decimal("188300")

    def test_balance_is_zero_at_full_term(self):
        assert remaining_balance(200000, "0.07", 30, 360) == Decimal("0.00")

    def test_balance_never_goes_negative_past_term(self):
        assert remaining_balance(200000, "0.07", 30, 500) == Decimal("0.00")

    def test_interest_only_balance_never_amortizes(self):
        assert remaining_balance(150000, "0.11", 30, 60, interest_only=True) == Decimal(
            "150000.00"
        )

    def test_zero_interest_balance_is_linear(self):
        assert remaining_balance(120000, "0", 10, 60) == Decimal("60000.00")


class TestInterest:
    def test_interest_only_interest_is_exact(self):
        # $135,000 at 11% for 6 months, interest only.
        assert total_interest_paid(135000, "0.11", 30, 6, interest_only=True) == Decimal(
            "7425.00"
        )

    def test_amortizing_interest_matches_schedule(self):
        rows = amortization_schedule(200000, "0.07", 30, months=24)
        summed = sum(r.interest for r in rows)
        closed_form = total_interest_paid(200000, "0.07", 30, 24)
        # Closed form vs. period-by-period accumulation: agree within rounding.
        assert abs(summed - closed_form) < Decimal("1.00")

    def test_no_interest_over_zero_months(self):
        assert total_interest_paid(200000, "0.07", 30, 0) == Decimal("0")


class TestAmortizationSchedule:
    def test_schedule_length_and_final_balance(self):
        rows = amortization_schedule(100000, "0.06", 30)
        assert len(rows) == 360
        assert rows[-1].balance == Decimal("0.00")

    def test_principal_grows_over_time(self):
        rows = amortization_schedule(100000, "0.06", 30, months=120)
        assert rows[0].principal < rows[-1].principal

    def test_interest_only_schedule_pays_no_principal(self):
        rows = amortization_schedule(100000, "0.10", 30, months=6, interest_only=True)
        assert all(r.principal == 0 for r in rows)
        assert rows[-1].balance == Decimal("100000.00")

    def test_empty_when_no_principal(self):
        assert amortization_schedule(0, "0.06", 30) == []


class TestDscr:
    def test_normal_dscr(self):
        assert dscr(30000, 24000) == Decimal("1.2500")

    def test_no_debt_means_undefined_not_infinite(self):
        # A free-and-clear property has no coverage ratio; it has no debt.
        assert dscr(30000, 0) is None

    def test_negative_noi_produces_negative_dscr(self):
        assert dscr(-5000, 24000) < 0
