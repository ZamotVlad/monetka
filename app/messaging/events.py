from typing import Any
from uuid import UUID

from app.db.uow import UnitOfWork

TOPIC = "monetka.events"


class EventType:
    WALLET_CHANGED = "wallet.changed"
    PAYMENT_UPDATED = "payment.updated"
    DEPOSIT_UPDATED = "deposit.updated"


def record_for_user(uow: UnitOfWork, user_id: UUID, type_: str, payload: dict[str, Any]) -> None:
    # The user id is the Kafka key: one user's events land in one partition, in order
    uow.outbox.add(TOPIC, str(user_id), type_, {"user_id": str(user_id), **payload})
