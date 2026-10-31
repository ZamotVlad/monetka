from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account, Merchant
from app.domain.errors import NotFound


class MerchantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, merchant: Merchant) -> None:
        self._session.add(merchant)

    async def by_api_key_hash(self, api_key_hash: str) -> Merchant | None:
        return await self._session.scalar(
            select(Merchant).where(Merchant.api_key_hash == api_key_hash)
        )

    async def account_of(self, merchant: Merchant) -> Account:
        account = await self._session.scalar(
            select(Account).where(Account.merchant_id == merchant.id)
        )
        if account is None:
            raise NotFound("Merchant account not found")
        return account
