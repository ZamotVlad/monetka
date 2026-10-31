from app.db.models import ReconciliationRun
from app.db.uow import UnitOfWork


class ReconciliationService:
    """Proves the books from scratch instead of trusting the cached balances.

    Three checks: every account's balance equals the sum of its entries, every transaction
    sums to zero, and all balances together sum to zero (money only moved, never appeared).
    """

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def run(self) -> ReconciliationRun:
        # One snapshot for all three queries; otherwise a transfer committing between them
        # would look like a mismatch
        await self._uow.session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        drifted = await self._uow.reconciliation.drifted_accounts()
        unbalanced = await self._uow.reconciliation.unbalanced_transactions()
        accounts, books_total = await self._uow.reconciliation.totals()
        run = ReconciliationRun(
            ok=not drifted and not unbalanced and books_total == 0,
            accounts_checked=accounts,
            books_total=books_total,
            problems={"drifted_accounts": drifted, "unbalanced_transactions": unbalanced},
        )
        self._uow.reconciliation.add_run(run)
        await self._uow.session.flush()
        return run
