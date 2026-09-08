"""Decimal money and rate primitives.

Every number that flows through the Atlas financial engine is a ``Decimal``.
Floats are never used for money: they make results non-reproducible across
platforms and produce artifacts like ``0.1 + 0.2 == 0.30000000000000004``.

Rounding policy
---------------
Intermediate arithmetic runs at full ``Decimal`` precision (28 significant
digits). Rounding happens only at the boundary, when a result is emitted:

* money  -> 2 decimal places, ROUND_HALF_UP (what a human expects)
* rates  -> 6 decimal places (0.0825 = 8.25%)
* ratios -> 4 decimal places (ROI, DSCR, margins)

This keeps every published number reproducible from its inputs.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional, Union

Numeric = Union[int, float, str, Decimal]

ZERO = Decimal("0")
ONE = Decimal("1")
CENT = Decimal("0.01")
RATE_Q = Decimal("0.000001")
RATIO_Q = Decimal("0.0001")
MONTHS_PER_YEAR = Decimal("12")


class MoneyError(ValueError):
    """Raised when a value cannot be interpreted as a decimal quantity."""


def D(value: Numeric) -> Decimal:
    """Coerce a value to ``Decimal`` without float contamination.

    Floats are routed through ``repr`` so that ``D(0.1)`` is ``Decimal("0.1")``
    rather than the binary expansion.
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):  # bool is an int subclass; almost always a bug
        raise MoneyError("boolean is not a valid numeric value")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(repr(value))
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "").replace("$", "")
        if cleaned.endswith("%"):
            try:
                return Decimal(cleaned[:-1]) / Decimal(100)
            except InvalidOperation as exc:
                raise MoneyError(f"cannot parse percentage: {value!r}") from exc
        try:
            return Decimal(cleaned)
        except InvalidOperation as exc:
            raise MoneyError(f"cannot parse decimal: {value!r}") from exc
    raise MoneyError(f"unsupported numeric type: {type(value).__name__}")


def money(value: Numeric) -> Decimal:
    """Round to cents, ROUND_HALF_UP."""
    return D(value).quantize(CENT, rounding=ROUND_HALF_UP)


def rate(value: Numeric) -> Decimal:
    """Round an interest/percentage rate to 6dp."""
    return D(value).quantize(RATE_Q, rounding=ROUND_HALF_UP)


def ratio(value: Numeric) -> Decimal:
    """Round a derived ratio (ROI, DSCR, margin) to 4dp."""
    return D(value).quantize(RATIO_Q, rounding=ROUND_HALF_UP)


def safe_div(numerator: Numeric, denominator: Numeric) -> Optional[Decimal]:
    """Divide, returning ``None`` when the denominator is zero.

    A ``None`` here means "undefined", which is a materially different
    statement than "zero" and is carried through to the API as ``null`` so the
    UI never prints a fabricated 0% return.
    """
    den = D(denominator)
    if den == 0:
        return None
    return D(numerator) / den


def pct_of(base: Numeric, percentage: Numeric) -> Decimal:
    """``percentage`` expressed as a fraction (0.06) applied to ``base``."""
    return D(base) * D(percentage)


def non_negative(value: Numeric) -> Decimal:
    """Floor a value at zero. Used where a negative is nonsensical (e.g. a fee)."""
    v = D(value)
    return v if v > 0 else ZERO
