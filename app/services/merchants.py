from app.db.models import Account, Merchant
from app.db.uow import UnitOfWork
from app.domain.ledger import AccountKind
from app.security import generate_api_key, hash_api_key


class MerchantService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def create(self, name: str, api_key: str | None = None) -> tuple[Merchant, str]:
        """Returns the API key in clear text once; only its hash is stored.

        A fixed key is accepted only for demo data, so the demo till works without copying it.
        """
        api_key = api_key or generate_api_key()
        merchant = Merchant(name=name, api_key_hash=hash_api_key(api_key))
        self._uow.merchants.add(merchant)
        await self._uow.session.flush()
        self._uow.accounts.add(Account(kind=AccountKind.MERCHANT, merchant_id=merchant.id))
        await self._uow.session.flush()
        return merchant, api_key

    async def authenticate(self, api_key: str) -> Merchant | None:
        return await self._uow.merchants.by_api_key_hash(hash_api_key(api_key))
