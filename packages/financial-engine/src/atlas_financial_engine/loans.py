"""Loan mathematics.

Pure, deterministic, dependency-free. Every function here is exercised directly
by the test-suite because everything downstream inherits its errors.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional

from .money import D, MONTHS_PER_YEAR, Numeric, ZERO, money, ratio


@dataclass(frozen=True)
class AmortizationRow:
    period: int
    payment: Decimal
    interest: Decimal
    principal: Decimal
    balance: Decimal


def monthly_rate(annual_rate: Numeric) -> Decimal:
    return D(annual_rate) / MONTHS_PER_YEAR


def payment_factor(annual_rate: Numeric, amortization_years: int) -> Decimal:
    """Monthly payment per $1 of loan for a fully-amortizing loan.

    ``i * (1+i)^n / ((1+i)^n - 1)``; degenerates to ``1/n`` at 0% interest.
    """
    n = int(amortization_years) * 12
    if n <= 0:
        raise ValueError("amortization_years must be positive")
    i = monthly_rate(annual_rate)
    if i == 0:
        return D(1) / D(n)
    growth = (D(1) + i) ** n
    return i * growth / (growth - D(1))


def monthly_payment(
    principal: Numeric,
    annual_rate: Numeric,
    amortization_years: int,
    interest_only: bool = False,
) -> Decimal:
    """Monthly debt service. Interest-only loans pay ``principal * i``."""
    p = D(principal)
    if p <= 0:
        return ZERO
    if interest_only:
        return money(p * monthly_rate(annual_rate))
    return money(p * payment_factor(annual_rate, amortization_years))


def remaining_balance(
    principal: Numeric,
    annual_rate: Numeric,
    amortization_years: int,
    months_elapsed: int,
    interest_only: bool = False,
) -> Decimal:
    """Balance after ``months_elapsed`` scheduled payments.

    Uses the closed-form balance formula rather than iterating, so a 30-year
    balloon computation is O(1) and free of accumulated rounding drift.
    """
    p = D(principal)
    if p <= 0:
        return ZERO
    if interest_only:
        return money(p)
    n = int(amortization_years) * 12
    m = min(int(months_elapsed), n)
    if m <= 0:
        return money(p)
    i = monthly_rate(annual_rate)
    if i == 0:
        return money(p * (D(1) - D(m) / D(n)))
    growth = (D(1) + i) ** n
    growth_m = (D(1) + i) ** m
    balance = p * (growth - growth_m) / (growth - D(1))
    return money(max(balance, ZERO))


def total_interest_paid(
    principal: Numeric,
    annual_rate: Numeric,
    amortization_years: int,
    months: int,
    interest_only: bool = False,
) -> Decimal:
    """Interest paid over the first ``months`` payments."""
    p = D(principal)
    if p <= 0 or months <= 0:
        return ZERO
    if interest_only:
        return money(p * monthly_rate(annual_rate) * D(months))
    pmt = monthly_payment(p, annual_rate, amortization_years, interest_only=False)
    n = int(amortization_years) * 12
    m = min(int(months), n)
    balance = remaining_balance(p, annual_rate, amortization_years, m)
    principal_paid = p - balance
    return money(pmt * D(m) - principal_paid)


def amortization_schedule(
    principal: Numeric,
    annual_rate: Numeric,
    amortization_years: int,
    months: Optional[int] = None,
    interest_only: bool = False,
) -> List[AmortizationRow]:
    """Period-by-period schedule. Used for balloon/seller-finance disclosure."""
    p = D(principal)
    n = int(amortization_years) * 12
    limit = n if months is None else min(int(months), n)
    if p <= 0 or limit <= 0:
        return []
    i = monthly_rate(annual_rate)
    pmt = monthly_payment(p, annual_rate, amortization_years, interest_only)
    balance = p
    rows: List[AmortizationRow] = []
    for period in range(1, limit + 1):
        interest = balance * i
        if interest_only:
            # An interest-only note never amortizes; it balloons. The running
            # balance is what the borrower owes at payoff.
            principal_part = ZERO
        else:
            principal_part = pmt - interest
            # The scheduled payment is rounded to cents, so it does not divide
            # the balance exactly. Lenders absorb the difference in the final
            # payment; so do we, rather than leaving a phantom balance.
            if period == n or principal_part > balance:
                principal_part = balance
        balance = balance - principal_part
        rows.append(
            AmortizationRow(
                period=period,
                payment=money(interest + principal_part),
                interest=money(interest),
                principal=money(principal_part),
                balance=money(balance),
            )
        )
    return rows


def loan_amount(
    purchase_price: Numeric,
    rehab: Numeric,
    loan_to_purchase: Numeric,
    loan_to_rehab: Numeric,
) -> Decimal:
    return D(purchase_price) * D(loan_to_purchase) + D(rehab) * D(loan_to_rehab)


def dscr(net_operating_income: Numeric, annual_debt_service: Numeric) -> Optional[Decimal]:
    """Debt service coverage ratio. ``None`` when there is no debt.

    Returning ``None`` rather than infinity keeps the meaning honest: a
    free-and-clear property has no coverage ratio, it has no debt.
    """
    ads = D(annual_debt_service)
    if ads <= 0:
        return None
    return ratio(D(net_operating_income) / ads)
