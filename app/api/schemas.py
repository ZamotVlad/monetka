from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import (
    AliasChoices,
    AliasPath,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)

# Amounts travel as integer kopiyky, like Stripe's cents: no float rounding on the wire
Amount = Field(gt=0, le=100_000_000, description="Minor units, 8600 = 86.00 UAH")


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def fits_bcrypt(cls, value: str) -> str:
        # bcrypt only reads 72 bytes; a longer UTF-8 password would be silently truncated
        if len(value.encode()) > 72:
            raise ValueError("Password is too long")
        return value


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    is_operator: bool


class BalanceOut(BaseModel):
    available: int
    held: int
    total: int
    currency: str = "UAH"


class HistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    details: dict[str, Any]
    created_at: datetime
    wallet_delta: int
    held_delta: int


class HistoryPage(BaseModel):
    items: list[HistoryItem]
    next_before: int | None


class TransferIn(BaseModel):
    to_email: EmailStr
    amount: int = Amount
    note: str | None = Field(default=None, max_length=140)


class WithdrawalIn(BaseModel):
    amount: int = Amount
    card_last4: str = Field(pattern=r"^\d{4}$")


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    details: dict[str, Any]
    created_at: datetime


class PaymentRequestIn(BaseModel):
    customer_email: EmailStr
    amount: int = Amount
    description: str = Field(min_length=1, max_length=140)


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    # Read from the ORM object and from a stored idempotent response alike
    merchant_name: str = Field(
        validation_alias=AliasChoices(AliasPath("merchant", "name"), "merchant_name")
    )
    amount: int
    description: str
    status: str
    expires_at: datetime
    created_at: datetime


class MerchantPaymentOut(PaymentOut):
    customer_id: UUID = Field(validation_alias=AliasChoices("user_id", "customer_id"))
