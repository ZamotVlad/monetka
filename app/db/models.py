from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Identity,
    String,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    is_operator: Mapped[bool] = mapped_column(default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        # The last line of defence: even a bug in the service layer cannot overdraw a wallet
        CheckConstraint("allow_negative OR balance >= 0", name="balance_not_negative"),
        UniqueConstraint("user_id", "kind"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    kind: Mapped[str] = mapped_column(String(16))
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    currency: Mapped[str] = mapped_column(String(3), default="UAH", server_default="UAH")
    # A cached sum of the entries, kept so a balance check is one row read, not a SUM
    balance: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    allow_negative: Mapped[bool] = mapped_column(default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class LedgerTransaction(Base):
    __tablename__ = "ledger_transactions"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    details: Mapped[dict[str, Any]] = mapped_column(
        default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    entries: Mapped[list["LedgerEntry"]] = relationship(lazy="raise")


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (CheckConstraint("amount <> 0", name="amount_not_zero"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("ledger_transactions.id"), index=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    amount: Mapped[int] = mapped_column(BigInteger)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    scope: Mapped[str] = mapped_column(String(64), primary_key=True)
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    status_code: Mapped[int | None]
    response_body: Mapped[dict[str, Any] | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
