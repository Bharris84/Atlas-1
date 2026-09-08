"""Buy & hold rental model."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from atlas_financial_engine import (
    DealInputs,
    FinancingTerms,
    RentalAssumptions,
    analyze_buy_hold,
    build_operating_statement,
)
from atlas_financial_engine.assumptions import CASH_PURCHASE
from atlas_financial_engine.money import D


def _rental(**kwargs) -> RentalAssumptions:
    base = dict(annual_taxes=D("2400"), annual_insurance=D("1800"))
    base.update(kwargs)
    return RentalAssumptions(**base)


class TestOperatingStatement:
    def test_gross_scheduled_rent_is_annualised(self):
        ops = build_operating_statement(D("1800"), _rental())
        assert ops.gross_scheduled_rent == D("21600.00")

    def test_vacancy_is_a_percentage_of_gross_rent(self):
        ops = build_operating_statement(D("1800"), _rental())
        assert ops.vacancy_loss == D("1080.00")  # 5% of $21,600
        assert ops.effective_gross_income == D("20520.00")

    def test_management_is_charged_on_collected_rent(self):
        """Management agreements are written on rent collected, not scheduled."""
        ops = build_operating_statement(D("1800"), _rental())
        assert ops.management == D("1641.60")  # 8% of $20,520

    def test_reserves_are_charged_on_scheduled_rent(self):
        """A vacant unit still ages; reserves do not pause during vacancy."""
        ops = build_operating_statement(D("1800"), _rental())
        assert ops.maintenance == D("1080.00")  # 5% of $21,600
        assert ops.capex == D("1080.00")

    def test_noi_is_effective_income_less_all_operating_expenses(self):
        ops = build_operating_statement(D("1800"), _rental())
        assert ops.net_operating_income == ops.effective_gross_income - (
            ops.total_operating_expenses
        )

    def test_noi_excludes_debt_service(self):
        """NOI is a property-level number; financing is an investor-level choice."""
        ops = build_operating_statement(D("1800"), _rental())
        expected = D("20520.00") - (
            D("1641.60") + D("1080.00") + D("1080.00") + D("2400") + D("1800")
        )
        assert ops.net_operating_income == expected

    def test_hoa_is_annualised_from_a_monthly_figure(self):
        with_hoa = build_operating_statement(D("1800"), _rental(monthly_hoa=D("125")))
        without = build_operating_statement(D("1800"), _rental())
        assert without.net_operating_income - with_hoa.net_operating_income == D("1500.00")

    def test_all_expense_percentages_are_configurable(self):
        lean = build_operating_statement(
            D("1800"),
            _rental(
                vacancy_percent=D("0"),
                management_percent=D("0"),
                maintenance_percent=D("0"),
                capex_percent=D("0"),
            ),
        )
        assert lean.net_operating_income == D("21600.00") - D("4200")


class TestReturns:
    def test_cap_rate_is_noi_over_purchase_price(self, baseline: DealInputs):
        result = analyze_buy_hold(baseline)
        noi = D(result.detail["operating_statement"]["net_operating_income"])
        assert abs(result.cap_rate - noi / D("150000")) < D("0.0001")

    def test_dscr_is_noi_over_annual_debt_service(self, baseline: DealInputs):
        result = analyze_buy_hold(baseline)
        noi = D(result.detail["operating_statement"]["net_operating_income"])
        assert abs(result.dscr - noi / D(result.detail["annual_debt_service"])) < D("0.0001")

    def test_cash_flow_is_noi_less_debt_service(self, baseline: DealInputs):
        result = analyze_buy_hold(baseline)
        noi = D(result.detail["operating_statement"]["net_operating_income"])
        assert result.annual_cash_flow == noi - D(result.detail["annual_debt_service"])

    def test_cash_on_cash_is_annual_cash_flow_over_cash_invested(
        self, baseline: DealInputs
    ):
        result = analyze_buy_hold(baseline)
        assert abs(
            result.cash_on_cash - result.annual_cash_flow / result.cash_required
        ) < D("0.0001")

    def test_all_cash_purchase_has_no_dscr(self, baseline: DealInputs):
        """No debt means no coverage ratio — undefined, not infinite."""
        all_cash = replace(
            baseline,
            assumptions=replace(
                baseline.assumptions, rental=_rental(financing=CASH_PURCHASE)
            ),
        )
        result = analyze_buy_hold(all_cash)
        assert result.dscr is None
        assert result.annual_cash_flow == D(
            result.detail["operating_statement"]["net_operating_income"]
        )

    def test_cash_required_is_down_payment_plus_costs(self, baseline: DealInputs):
        d = analyze_buy_hold(baseline).detail
        expected = (
            D(d["down_payment"])
            + D(d["acquisition_closing_costs"])
            + D(d["rehab"])
            + D(d["points_cost"])
            + D(d["lender_fees"])
        )
        assert D(d["cash_required"]) == expected


class TestBuyBoxAndMaxPrice:
    def test_max_price_is_the_tightest_of_the_three_constraints(
        self, baseline: DealInputs
    ):
        d = analyze_buy_hold(baseline).detail
        constraints = [
            D(d[k])
            for k in (
                "max_price_for_cash_flow",
                "max_price_for_dscr",
                "max_price_for_cash_on_cash",
            )
            if d[k] is not None
        ]
        assert analyze_buy_hold(baseline).max_purchase_price == min(constraints)

    def test_buying_at_max_price_meets_the_buy_box(self, baseline: DealInputs):
        max_price = analyze_buy_hold(baseline).max_purchase_price
        at_max = analyze_buy_hold(replace(baseline, purchase_price=max_price, rehab=D("0")))
        assert at_max.meets_criteria is True

    def test_higher_rent_raises_the_price_we_can_pay(self, baseline: DealInputs):
        assert (
            analyze_buy_hold(replace(baseline, monthly_rent=D("2400"))).max_purchase_price
            > analyze_buy_hold(baseline).max_purchase_price
        )

    def test_criteria_cover_cash_flow_coc_and_dscr(self, baseline: DealInputs):
        names = {c.name for c in analyze_buy_hold(baseline).criteria}
        assert names == {
            "minimum_monthly_cash_flow",
            "minimum_cash_on_cash",
            "target_dscr",
        }


class TestWarningsAndEdges:
    def test_negative_cash_flow_is_surfaced(self, baseline: DealInputs):
        expensive = replace(baseline, purchase_price=D("300000"))
        result = analyze_buy_hold(expensive)
        assert result.monthly_cash_flow < 0
        assert any("Negative cash flow" in w for w in result.warnings)

    def test_zero_taxes_are_flagged_as_an_understated_expense(self, baseline: DealInputs):
        no_taxes = replace(
            baseline,
            assumptions=replace(
                baseline.assumptions,
                rental=RentalAssumptions(annual_taxes=D("0"), annual_insurance=D("1800")),
            ),
        )
        assert any("taxes are set to zero" in w for w in analyze_buy_hold(no_taxes).warnings)

    def test_dscr_below_one_is_flagged(self, baseline: DealInputs):
        strained = replace(baseline, purchase_price=D("300000"))
        result = analyze_buy_hold(strained)
        assert result.dscr < 1
        assert any("below 1.0" in w for w in result.warnings)

    def test_zero_rent_produces_negative_cash_flow_not_an_error(
        self, baseline: DealInputs
    ):
        """A vacant property is a real situation, not an input error."""
        vacant = replace(baseline, monthly_rent=D("0"))
        result = analyze_buy_hold(vacant)
        assert result.viable is True
        assert result.annual_cash_flow < 0

    @pytest.mark.parametrize("field", ["purchase_price", "monthly_rent"])
    def test_missing_required_input_is_not_viable(self, baseline: DealInputs, field):
        result = analyze_buy_hold(replace(baseline, **{field: None}))
        assert result.viable is False
        assert field in result.missing_inputs

    def test_extreme_interest_rate_still_computes(self, baseline: DealInputs):
        painful = replace(
            baseline,
            assumptions=replace(
                baseline.assumptions,
                rental=_rental(
                    financing=FinancingTerms(
                        annual_interest_rate=D("0.30"), interest_only=False
                    )
                ),
            ),
        )
        result = analyze_buy_hold(painful)
        assert result.viable is True
        assert result.dscr < analyze_buy_hold(baseline).dscr
