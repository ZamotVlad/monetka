"""Double-entry bookkeeping without a database.

Every movement of money is a transaction made of postings. A posting adds a signed amount to
one account. The postings of a transaction always sum to zero, so money is never created or
destroyed inside the system, it only moves. That single rule is what lets reconciliation
prove the books are right.
"""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.domain.errors import InsufficientFunds, InvalidAmount, UnbalancedTransaction
from app.domain.money import Money

# The payment provider's side of the books. It goes negative as users top up, which is
# exactly how much real money the provider holds for us.
PSP_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000001")


class AccountKind(StrEnum):
    WALLET = "wallet"
    HOLD = "hold"
    MERCHANT = "merchant"
    SYSTEM = "system"


class TransactionKind(StrEnum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER = "transfer"
    HOLD = "hold"
    CAPTURE = "capture"
    RELEASE = "release"


@dataclass(frozen=True, slots=True)
class Posting:
    account_id: UUID
    amount: Money


def move(source: UUID, target: UUID, amount: Money) -> list[Posting]:
    if not amount.is_positive:
        raise InvalidAmount("Amount must be positive")
    return [Posting(source, -amount), Posting(target, amount)]


def validate(postings: Sequence[Posting]) -> None:
    if len(postings) < 2:
        raise UnbalancedTransaction("A transaction needs at least two postings")
    currencies = {posting.amount.currency for posting in postings}
    if len(currencies) != 1:
        raise UnbalancedTransaction("All postings must use one currency")
    if any(posting.amount.amount == 0 for posting in postings):
        raise UnbalancedTransaction("Zero postings are noise in the books")
    if sum(posting.amount.amount for posting in postings) != 0:
        raise UnbalancedTransaction("Postings must sum to zero")


def apply(
    balances: Mapping[UUID, int],
    postings: Sequence[Posting],
    overdraft_allowed: Collection[UUID] = (),
) -> dict[UUID, int]:
    """Return the new balances, or raise before anything is changed."""
    validate(postings)
    result = dict(balances)
    for posting in postings:
        result[posting.account_id] = result[posting.account_id] + posting.amount.amount
    for posting in postings:
        account_id = posting.account_id
        if result[account_id] < 0 and account_id not in overdraft_allowed:
            raise InsufficientFunds("Not enough money on the account")
    return result
