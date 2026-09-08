"""Seller financing model."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from atlas_financial_engine import (
    DealInputs,
    SellerFinanceAssumptions,
    analyze_seller_finance,
)
from atlas_financial_engine.loans import monthly_payment
from atlas_financial_engine.money import D


class TestTerms:
    def test_down_payment_and_financed_amount_split_the_price(self, baseline: DealInputs):
        d = analyze_seller_finance(baseline).detail
        assert D(d["down_payment"]) == D("15000.00")  # 10% of $150,000
        assert D(d["financed_amount"]) == D("135000.00")

    def test_payment_matches_the_amortisation_formula(self, baseline: DealInputs):
        d = analyze_seller_finance(baseline).detail
        assert D(d["monthly_principal_and_interest"]) == monthly_payment(
            D("135000"), D("0.06"), 30
        )

    def test_low_down_payment_trades_cash_flow_for_capital_efficiency(
        self, baseline: DealInputs
    ):
        """10% down on seller terms vs 25% down at a bank.

        Less cash goes in, but more is financed, so monthly cash flow is
        actually LOWER while the return on the cash invested is higher. That
        trade is the whole point of buying on terms, and the engine must show
        both sides of it rather than flattering the strategy.
        """
        from atlas_financial_engine import analyze_buy_hold

        sf = analyze_seller_finance(baseline)
        bank = analyze_buy_hold(baseline)
        assert sf.cash_required < bank.cash_required
        assert sf.monthly_cash_flow < bank.monthly_cash_flow
        assert sf.cash_on_cash > bank.cash_on_cash

    def test_interest_rate_is_configurable(self, baseline: DealInputs):
        pricey = replace(
            baseline,
            assumptions=replace(
                baseline.assumptions,
                seller_finance=SellerFinanceAssumptions(annual_interest_rate=D("0.09")),
            ),
        )
        assert (
            analyze_seller_finance(pricey).monthly_cash_flow
            < analyze_seller_finance(baseline).monthly_cash_flow
        )

    def test_zero_percent_seller_note_is_supported(self, baseline: DealInputs):
        free_money = replace(
            baseline,
            assumptions=replace(
                baseline.assumptions,
                seller_finance=SellerFinanceAssumptions(annual_interest_rate=D("0")),
            ),
        )
        d = analyze_seller_finance(free_money).detail
        # 0% over 30 years is simply the balance divided by 360 payments.
        assert D(d["monthly_principal_and_interest"]) == D("375.00")
        assert D(d["interest_paid_through_balloon"]) == 0


class TestBalloon:
    def test_balloon_balance_is_reported(self, baseline: DealInputs):
        d = analyze_seller_finance(baseline).detail
        assert D(d["balloon_balance"]) > 0
        assert D(d["balloon_balance"]) < D(d["financed_amount"])

    def test_balloon_is_warned_about_up_front(self, baseline: DealInputs):
        assert any(
            "balloon payment" in w for w in analyze_seller_finance(baseline).warnings
        )

    def test_time_to_liquidity_is_the_balloon_horizon(self, baseline: DealInputs):
        assert analyze_seller_finance(baseline).time_to_liquidity_months == 60

    def test_no_balloon_is_supported(self, baseline: DealInputs):
        fully_amortising = replace(
            baseline,
            assumptions=replace(
                baseline.assumptions,
                seller_finance=SellerFinanceAssumptions(balloon_years=None),
            ),
        )
        result = analyze_seller_finance(fully_amortising)
        assert result.detail["balloon_balance"] is None
        assert result.time_to_liquidity_months is None

    def test_longer_balloon_leaves_a_smaller_balance(self, baseline: DealInputs):
        ten_year = replace(
            baseline,
            assumptions=replace(
                baseline.assumptions,
                seller_finance=SellerFinanceAssumptions(balloon_years=10),
            ),
        )
        assert D(analyze_seller_finance(ten_year).detail["balloon_balance"]) < D(
            analyze_seller_finance(baseline).detail["balloon_balance"]
        )


class TestReturns:
    def test_cash_required_is_down_payment_plus_closing_plus_rehab(
        self, baseline: DealInputs
    ):
        d = analyze_seller_finance(baseline).detail
        assert D(d["cash_required"]) == (
            D(d["down_payment"]) + D(d["closing_costs"]) + D("45000")
        )

    def test_cash_flow_is_noi_less_debt_service(self, baseline: DealInputs):
        result = analyze_seller_finance(baseline)
        noi = D(result.detail["operating_statement"]["net_operating_income"])
        assert result.annual_cash_flow == noi - D(result.detail["annual_debt_service"])

    def test_equity_accounts_for_the_rehab_spent_to_create_it(self, baseline: DealInputs):
        result = analyze_seller_finance(baseline)
        assert result.equity_created == D("250000") - D("150000") - D("45000")


class TestWarningsAndEdges:
    def test_high_seller_rate_is_flagged(self, baseline: DealInputs):
        expensive = replace(
            baseline,
            assumptions=replace(
                baseline.assumptions,
                seller_finance=SellerFinanceAssumptions(annual_interest_rate=D("0.12")),
            ),
        )
        assert any("above 10%" in w for w in analyze_seller_finance(expensive).warnings)

    def test_paying_over_value_is_named_as_a_trade_not_a_win(self, baseline: DealInputs):
        over = replace(baseline, purchase_price=D("270000"))
        assert any(
            "exceeds the estimated value" in w
            for w in analyze_seller_finance(over).warnings
        )

    def test_negative_cash_flow_is_surfaced(self, baseline: DealInputs):
        thin = replace(baseline, monthly_rent=D("700"))
        result = analyze_seller_finance(thin)
        assert result.monthly_cash_flow < 0
        assert any("Negative cash flow" in w for w in result.warnings)

    def test_without_rent_the_payment_still_computes(self, baseline: DealInputs):
        no_rent = replace(baseline, monthly_rent=None)
        result = analyze_seller_finance(no_rent)
        assert result.viable is True
        assert D(result.detail["monthly_principal_and_interest"]) > 0
        assert result.monthly_cash_flow is None

    def test_missing_purchase_price_is_not_viable(self, baseline: DealInputs):
        result = analyze_seller_finance(replace(baseline, purchase_price=None))
        assert result.viable is False
        assert "purchase_price" in result.missing_inputs
