"""A payment request from a shop goes through a small state machine.

PENDING     the shop asked, the customer has not answered yet
AUTHORIZED  the customer agreed, the money is reserved (on hold) but not paid
CAPTURED    the shop delivered and took the money
DECLINED / VOIDED / EXPIRED   nothing was paid, any reserve went back to the wallet

The same reserve-then-settle shape is how card payments and casino bets work.
"""

from enum import StrEnum

from app.domain.errors import InvalidTransition


class PaymentStatus(StrEnum):
    PENDING = "pending"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    DECLINED = "declined"
    VOIDED = "voided"
    EXPIRED = "expired"


TRANSITIONS: dict[PaymentStatus, frozenset[PaymentStatus]] = {
    PaymentStatus.PENDING: frozenset(
        {
            PaymentStatus.AUTHORIZED,
            PaymentStatus.DECLINED,
            PaymentStatus.VOIDED,
            PaymentStatus.EXPIRED,
        }
    ),
    PaymentStatus.AUTHORIZED: frozenset(
        {PaymentStatus.CAPTURED, PaymentStatus.VOIDED, PaymentStatus.EXPIRED}
    ),
}


def ensure_transition(current: PaymentStatus, target: PaymentStatus) -> None:
    if target not in TRANSITIONS.get(current, frozenset()):
        raise InvalidTransition(f"Payment is {current}, it cannot become {target}")
