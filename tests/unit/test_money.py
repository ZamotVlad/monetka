from decimal import Decimal

import pytest

from app.domain.errors import InvalidAmount
from app.domain.money import Money


def test_from_decimal_is_exact() -> None:
    assert Money.from_decimal("86.10").amount == 8610
    assert Money.from_decimal(Decimal("0.01")).amount == 1


def test_rejects_fractions_of_a_kopiyka() -> None:
    with pytest.raises(InvalidAmount):
        Money.from_decimal("1.005")


def test_rejects_float_and_bool() -> None:
    with pytest.raises(TypeError):
        Money(1.5)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Money(True)


def test_arithmetic_and_format() -> None:
    assert Money(500) + Money(250) == Money(750)
    assert -Money(100) == Money(-100)
    assert str(Money(8610)) == "86.10 UAH"


def test_unknown_currency() -> None:
    with pytest.raises(InvalidAmount):
        Money(100, "USD")
