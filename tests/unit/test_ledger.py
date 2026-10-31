import contextlib
from uuid import UUID, uuid4

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain import ledger
from app.domain.errors import InsufficientFunds, InvalidAmount, UnbalancedTransaction
from app.domain.ledger import Posting, move
from app.domain.money import Money

A, B, SYSTEM = uuid4(), uuid4(), uuid4()


def test_move_creates_balanced_pair() -> None:
    postings = move(A, B, Money(300))
    ledger.validate(postings)
    assert [p.amount.amount for p in postings] == [-300, 300]


def test_move_rejects_non_positive_amount() -> None:
    with pytest.raises(InvalidAmount):
        move(A, B, Money(0))


@pytest.mark.parametrize(
    "postings",
    [
        [Posting(A, Money(100))],
        [Posting(A, Money(-100)), Posting(B, Money(90))],
        [Posting(A, Money(0)), Posting(B, Money(0))],
    ],
)
def test_unbalanced_transactions_are_rejected(postings: list[Posting]) -> None:
    with pytest.raises(UnbalancedTransaction):
        ledger.validate(postings)


def test_apply_refuses_overdraft() -> None:
    with pytest.raises(InsufficientFunds):
        ledger.apply({A: 100, B: 0}, move(A, B, Money(101)))


def test_system_account_may_go_negative() -> None:
    balances = ledger.apply({SYSTEM: 0, A: 0}, move(SYSTEM, A, Money(500)), {SYSTEM})
    assert balances == {SYSTEM: -500, A: 500}


accounts = st.sampled_from([A, B, SYSTEM])
transfers = st.lists(
    st.tuples(accounts, accounts, st.integers(min_value=1, max_value=10_000)), max_size=60
)


@given(transfers)
def test_money_is_never_created_or_destroyed(moves: list[tuple[UUID, UUID, int]]) -> None:
    """Whatever random transfers happen, the books stay balanced and no wallet goes negative."""
    balances = {A: 0, B: 0, SYSTEM: 0}
    for source, target, amount in moves:
        if source == target:
            continue
        with contextlib.suppress(InsufficientFunds):
            balances = ledger.apply(balances, move(source, target, Money(amount)), {SYSTEM})
        assert sum(balances.values()) == 0
        assert balances[A] >= 0
        assert balances[B] >= 0
