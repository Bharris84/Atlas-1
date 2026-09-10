"""The shared cost model, and the linear form used to solve for max price.

The linear model is an optimisation: it lets Atlas answer "what is the most I
can pay?" exactly instead of by search. That optimisation is only safe if the
linear form agrees with the direct calculation, so that equivalence is tested
directly rather than assumed.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from atlas_financial_engine.assumptions import (
    CASH_PURCHASE,
    DEFAULT_HARD_MONEY,
    FinancingTerms,
    HoldingCosts,
    TransactionCosts,
)
from atlas_financial_engine.costs import (
    build_cost_model,
    compute_project_costs,
    interest_factor,
    max_price_for_profit,
    max_price_for_roi,
)
from atlas_financial_engine.money import D

TX = TransactionCosts()
# Utilities are stated explicitly: since expenses became tri-state there is
# no default figure to inherit, and an unstated one would be omitted.
HOLD = HoldingCosts(
    annual_taxes=D("2400"), annual_insurance=D("1800"), monthly_utilities=D("150")
)


def _costs(price, rehab="45000", financing=DEFAULT_HARD_MONEY, months=6, sale="250000"):
    return compute_project_costs(
        purchase_price=price,
        rehab_base=rehab,
        rehab_contingency="0.15",
        holding_months=months,
        transaction=TX,
        holding=HOLD,
        financing=financing,
        sale_price=sale,
    )


def _model(rehab="45000", financing=DEFAULT_HARD_MONEY, months=6, sale="250000"):
    return build_cost_model(
        sale_price=sale,
        rehab_base=rehab,
        rehab_contingency="0.15",
        holding_months=months,
        transaction=TX,
        holding=HOLD,
        financing=financing,
    )


class TestInterestFactor:
    def test_interest_only_factor_is_rate_times_months(self):
        # 12% annual, 6 months, interest only = 6% of principal.
        assert interest_factor("0.12", 30, 6, True) == D("0.06")

    def test_zero_months_costs_nothing(self):
        assert interest_factor("0.12", 30, 0, True) == 0

    def test_amortizing_factor_is_below_interest_only(self):
        # An amortizing loan pays down principal, so it accrues less interest.
        assert interest_factor("0.07", 30, 24, False) < interest_factor("0.07", 30, 24, True)


class TestProjectCosts:
    def test_rehab_contingency_is_applied(self):
        costs = _costs("150000")
        assert costs.rehab_contingency_amount == D("6750.00")
        assert costs.rehab_total == D("51750.00")

    def test_holding_cost_is_monthly_times_months(self):
        costs = _costs("150000")
        # ($2,400 + $1,800)/12 + $150 utilities = $500/mo.
        assert costs.monthly_holding_costs == D("500.00")
        assert costs.holding_costs == D("3000.00")

    def test_selling_costs_are_percent_of_sale_price(self):
        # 6% commission + 2% seller closing on a $250,000 sale.
        assert _costs("150000").selling_costs == D("20000.00")

    def test_cash_purchase_has_no_financing_costs(self):
        costs = _costs("150000", financing=CASH_PURCHASE)
        assert costs.financing.total == 0
        assert costs.financing.loan_amount == 0

    def test_cash_purchase_requires_the_whole_basis_in_cash(self):
        costs = _costs("150000", financing=CASH_PURCHASE)
        assert costs.cash_required == costs.total_basis

    def test_leverage_reduces_cash_but_raises_total_cost(self):
        cash_deal = _costs("150000", financing=CASH_PURCHASE)
        levered = _costs("150000", financing=DEFAULT_HARD_MONEY)
        assert levered.cash_required < cash_deal.cash_required
        assert levered.total_project_cost > cash_deal.total_project_cost

    def test_rehab_draw_factor_discounts_rehab_interest(self):
        """Rehab funds draw progressively, so full-term interest overstates cost."""
        full_draw = FinancingTerms(average_rehab_draw_factor=D("1.0"))
        partial = FinancingTerms(average_rehab_draw_factor=D("0.5"))
        assert _costs("150000", financing=partial).financing.interest_cost < _costs(
            "150000", financing=full_draw
        ).financing.interest_cost

    def test_total_basis_excludes_selling_costs(self):
        costs = _costs("150000")
        assert costs.total_project_cost - costs.total_basis == costs.selling_costs


class TestLinearModelEquivalence:
    """The linear form must agree with the direct calculation, everywhere."""

    @pytest.mark.parametrize("price", ["0", "50000", "150000", "400000"])
    def test_total_cost_matches_direct_calculation(self, price):
        assert abs(_model().total_cost.at(price) - _costs(price).total_project_cost) < D(
            "0.02"
        )

    @pytest.mark.parametrize("price", ["0", "50000", "150000", "400000"])
    def test_cash_required_matches_direct_calculation(self, price):
        assert abs(_model().cash_required.at(price) - _costs(price).cash_required) < D("0.02")

    @pytest.mark.parametrize(
        "financing", [CASH_PURCHASE, DEFAULT_HARD_MONEY, FinancingTerms(interest_only=False)]
    )
    def test_equivalence_holds_across_financing_types(self, financing):
        direct = _costs("150000", financing=financing)
        modelled = _model(financing=financing)
        assert abs(modelled.total_cost.at("150000") - direct.total_project_cost) < D("0.02")
        assert abs(modelled.cash_required.at("150000") - direct.cash_required) < D("0.02")

    def test_profit_model_matches_arv_minus_total_cost(self):
        direct = _costs("150000")
        expected = D("250000") - direct.total_project_cost
        assert abs(_model().profit.at("150000") - expected) < D("0.02")


class TestMaxPriceSolvers:
    def test_price_for_profit_round_trips(self):
        """Buying at the solved price must produce exactly the target profit."""
        model = _model()
        price = max_price_for_profit(model, "30000")
        assert abs(model.profit.at(price) - D("30000")) < D("1.00")

    def test_price_for_roi_round_trips(self):
        model = _model()
        price = max_price_for_roi(model, "0.20")
        realised = model.profit.at(price) / model.cash_required.at(price)
        assert abs(realised - D("0.20")) < D("0.0001")

    def test_higher_profit_target_lowers_max_price(self):
        model = _model()
        assert max_price_for_profit(model, "50000") < max_price_for_profit(model, "30000")

    def test_higher_rehab_lowers_max_price(self):
        assert max_price_for_profit(_model(rehab="90000"), "30000") < max_price_for_profit(
            _model(rehab="45000"), "30000"
        )

    def test_roi_solver_returns_none_when_unconstrained(self):
        """With no cash at risk and no price sensitivity there is no solution."""
        model = build_cost_model(
            sale_price="250000",
            rehab_base="0",
            rehab_contingency="0",
            holding_months=0,
            transaction=TransactionCosts(
                purchase_closing_percent=D("0"),
                sale_commission_percent=D("0"),
                sale_closing_percent=D("0"),
            ),
            holding=HoldingCosts(monthly_utilities=D("0")),
            financing=FinancingTerms(
                loan_to_purchase=D("1"),
                loan_to_rehab=D("1"),
                points=D("0"),
                annual_interest_rate=D("0"),
                lender_fees_flat=D("0"),
            ),
        )
        assert max_price_for_roi(model, "1") is None
