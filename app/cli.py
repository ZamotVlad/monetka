"""Admin commands: python -m app.cli --help"""

import argparse
import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import update

from app.config import get_settings
from app.db.models import User
from app.db.session import create_engine, create_session_factory
from app.db.uow import UnitOfWork
from app.services.merchants import MerchantService


@asynccontextmanager
async def unit_of_work() -> AsyncIterator[UnitOfWork]:
    engine = create_engine(get_settings().database_url)
    try:
        async with UnitOfWork(create_session_factory(engine)) as uow:
            yield uow
    finally:
        await engine.dispose()


async def create_merchant(name: str) -> None:
    async with unit_of_work() as uow:
        merchant, api_key = await MerchantService(uow).create(name)
        await uow.commit()
    print(f"Merchant {merchant.name} ({merchant.id})")
    print(f"API key, shown once: {api_key}")


async def make_operator(email: str) -> None:
    async with unit_of_work() as uow:
        user = await uow.users.by_email(email)
        if user is None:
            print(f"No user {email}")
            return
        await uow.session.execute(update(User).where(User.id == user.id).values(is_operator=True))
        await uow.commit()
    print(f"{email} is an operator now")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create-merchant", help="add a shop and print its API key").add_argument(
        "name"
    )
    commands.add_parser("make-operator", help="open the operator panel to a user").add_argument(
        "email"
    )
    args = parser.parse_args()
    if args.command == "create-merchant":
        asyncio.run(create_merchant(args.name))
    elif args.command == "make-operator":
        asyncio.run(make_operator(args.email))


if __name__ == "__main__":
    main()
