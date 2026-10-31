from dataclasses import dataclass
from decimal import Decimal
from typing import Self

from app.domain.errors import InvalidAmount

SUPPORTED_CURRENCIES = frozenset({"UAH"})
MINOR_UNITS = 100


@dataclass(frozen=True, slots=True)
class Money:
    """An amount in minor units (kopiyky). Integers only: 0.1 + 0.2 != 0.3 in float."""

    amount: int
    currency: str = "UAH"

    def __post_init__(self) -> None:
        # bool is a subclass of int, and True kopiyka is never what the caller meant
        if isinstance(self.amount, bool) or not isinstance(self.amount, int):
            raise TypeError("Money amount must be an int number of minor units")
        if self.currency not in SUPPORTED_CURRENCIES:
            raise InvalidAmount(f"Unsupported currency {self.currency}")

    @classmethod
    def from_decimal(cls, value: Decimal | str, currency: str = "UAH") -> Self:
        number = Decimal(value)
        minor = number * MINOR_UNITS
        if minor != minor.to_integral_value():
            raise InvalidAmount(f"{value} has more than two decimal places")
        return cls(int(minor), currency)

    def to_decimal(self) -> Decimal:
        return Decimal(self.amount) / MINOR_UNITS

    @property
    def is_positive(self) -> bool:
        return self.amount > 0

    def __add__(self, other: Self) -> Self:
        self._check_currency(other)
        return type(self)(self.amount + other.amount, self.currency)

    def __sub__(self, other: Self) -> Self:
        self._check_currency(other)
        return type(self)(self.amount - other.amount, self.currency)

    def __neg__(self) -> Self:
        return type(self)(-self.amount, self.currency)

    def __str__(self) -> str:
        return f"{self.to_decimal():.2f} {self.currency}"

    def _check_currency(self, other: "Money") -> None:
        if other.currency != self.currency:
            raise InvalidAmount(f"Cannot mix {self.currency} and {other.currency}")
