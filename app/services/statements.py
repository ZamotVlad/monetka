import csv
import io
import re
from datetime import UTC, datetime
from uuid import UUID

from app.db.models import Statement
from app.db.uow import UnitOfWork
from app.domain.errors import InvalidAmount
from app.domain.ledger import AccountKind
from app.domain.money import Money
from app.integrations.storage import FileStorage

PERIOD = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def month_bounds(period: str) -> tuple[datetime, datetime]:
    if not PERIOD.match(period):
        raise InvalidAmount("Period must look like 2026-10")
    year, month = map(int, period.split("-"))
    start = datetime(year, month, 1, tzinfo=UTC)
    end = datetime(year + month // 12, month % 12 + 1, 1, tzinfo=UTC)
    return start, end


def previous_period(now: datetime) -> str:
    year, month = (now.year, now.month - 1) if now.month > 1 else (now.year - 1, 12)
    return f"{year:04d}-{month:02d}"


class StatementService:
    def __init__(self, uow: UnitOfWork, storage: FileStorage) -> None:
        self._uow = uow
        self._storage = storage

    async def generate(self, user_id: UUID, period: str) -> Statement:
        since, until = month_bounds(period)
        accounts = await self._uow.accounts.of_user(user_id)
        rows = await self._uow.ledger.history(
            accounts[AccountKind.WALLET].id,
            accounts[AccountKind.HOLD].id,
            limit=None,
            since=since,
            until=until,
        )
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["date", "operation", "details", "available_change", "reserved_change"])
        for row in reversed(rows):
            writer.writerow(
                [
                    row.created_at.isoformat(timespec="seconds"),
                    row.kind,
                    "; ".join(f"{k}={v}" for k, v in row.details.items() if v),
                    Money(row.wallet_delta).to_decimal(),
                    Money(row.held_delta).to_decimal(),
                ]
            )
        key = f"statements/{user_id}/{period}.csv"
        # BOM so Excel opens Cyrillic merchant names correctly
        await self._storage.put(key, ("﻿" + buffer.getvalue()).encode(), "text/csv")
        return await self._uow.statements.save(user_id, period, key, len(rows))

    async def list_with_links(self, user_id: UUID) -> list[tuple[Statement, str]]:
        statements = await self._uow.statements.of_user(user_id)
        return [(s, await self._storage.download_url(s.object_key)) for s in statements]

    async def users_due(self, period: str) -> list[UUID]:
        since, until = month_bounds(period)
        return await self._uow.statements.users_missing(period, since, until)
