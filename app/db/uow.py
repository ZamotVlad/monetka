from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.accounts import AccountRepository
from app.repositories.deposits import DepositRepository
from app.repositories.idempotency import IdempotencyRepository
from app.repositories.ledger import LedgerRepository
from app.repositories.merchants import MerchantRepository
from app.repositories.outbox import OutboxRepository
from app.repositories.payments import PaymentRepository
from app.repositories.reconciliation import ReconciliationRepository
from app.repositories.statements import StatementRepository
from app.repositories.users import UserRepository


class UnitOfWork:
    """One database transaction and the repositories that share it.

    Services change data through the repositories, the caller decides when to commit.
    Leaving the block without commit rolls everything back, so a failed operation never
    leaves half of a money movement in the database.
    """

    session: AsyncSession
    users: UserRepository
    accounts: AccountRepository
    ledger: LedgerRepository
    idempotency: IdempotencyRepository
    merchants: MerchantRepository
    payments: PaymentRepository
    deposits: DepositRepository
    outbox: OutboxRepository
    reconciliation: ReconciliationRepository
    statements: StatementRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __aenter__(self) -> Self:
        self.session = self._session_factory()
        self.users = UserRepository(self.session)
        self.accounts = AccountRepository(self.session)
        self.ledger = LedgerRepository(self.session)
        self.idempotency = IdempotencyRepository(self.session)
        self.merchants = MerchantRepository(self.session)
        self.payments = PaymentRepository(self.session)
        self.deposits = DepositRepository(self.session)
        self.outbox = OutboxRepository(self.session)
        self.reconciliation = ReconciliationRepository(self.session)
        self.statements = StatementRepository(self.session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.session.rollback()
        await self.session.close()

    async def commit(self) -> None:
        await self.session.commit()
