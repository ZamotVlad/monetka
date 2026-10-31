import pytest

from app.domain.errors import InvalidTransition
from app.domain.payments import TRANSITIONS, PaymentStatus, ensure_transition

ALLOWED = [(source, target) for source, targets in TRANSITIONS.items() for target in targets]
FORBIDDEN = [
    (source, target)
    for source in PaymentStatus
    for target in PaymentStatus
    if (source, target) not in ALLOWED
]


@pytest.mark.parametrize(("source", "target"), ALLOWED)
def test_allowed_transitions(source: PaymentStatus, target: PaymentStatus) -> None:
    ensure_transition(source, target)


@pytest.mark.parametrize(("source", "target"), FORBIDDEN)
def test_everything_else_is_refused(source: PaymentStatus, target: PaymentStatus) -> None:
    with pytest.raises(InvalidTransition):
        ensure_transition(source, target)


def test_final_states_are_final() -> None:
    final = {PaymentStatus.CAPTURED, PaymentStatus.DECLINED, PaymentStatus.VOIDED}
    assert not final & TRANSITIONS.keys()
