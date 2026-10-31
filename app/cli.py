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
from app.domain.ledger import PSP_ACCOUNT_ID, TransactionKind, move
from app.domain.money import Money
from app.services.auth import AuthService
from app.services.ledger import LedgerService
from app.services.merchants import MerchantService
from app.services.payments import PaymentService
from app.services.wallet import WalletService


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


DEMO_PASSWORD = "demo-password"
# Public on purpose, like the passwords above: demo data is for local runs only
DEMO_SHOP_KEY = "mk_demo_zerno"


async def seed_demo() -> None:
    """Two people, a coffee shop, an operator and a bit of history to click through."""
    settings = get_settings()
    async with unit_of_work() as uow:
        if await uow.users.by_email("olena@monetka.demo"):
            print("Demo data is already there")
            return
        auth = AuthService(uow, settings)
        olena = await auth.register("olena@monetka.demo", DEMO_PASSWORD)
        taras = await auth.register("taras@monetka.demo", DEMO_PASSWORD)
        operator = await auth.register("ops@monetka.demo", DEMO_PASSWORD)
        operator.is_operator = True
        ledger = LedgerService(uow)
        for user, amount in ((olena, 250_000), (taras, 50_000)):
            wallet = await uow.accounts.wallet_of(user.id)
            await ledger.post(
                TransactionKind.DEPOSIT,
                move(PSP_ACCOUNT_ID, wallet.id, Money(amount)),
                {"card": "4242"},
            )
        await WalletService(uow).transfer(taras, olena.email, Money(15_000), "За квитки")
        merchant, api_key = await MerchantService(uow).create("Кав'ярня «Зерно»", DEMO_SHOP_KEY)
        await PaymentService(uow, settings).request(
            merchant, olena.email, Money(8_600), "Лате і круасан"
        )
        await uow.commit()
    print(f"Users (password {DEMO_PASSWORD}): olena@monetka.demo, taras@monetka.demo")
    print("Operator: ops@monetka.demo")
    print(f"Shop API key for {merchant.name}: {api_key}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create-merchant", help="add a shop and print its API key").add_argument(
        "name"
    )
    commands.add_parser("make-operator", help="open the operator panel to a user").add_argument(
        "email"
    )
    commands.add_parser("seed-demo", help="fill an empty database with demo data")
    args = parser.parse_args()
    if args.command == "create-merchant":
        asyncio.run(create_merchant(args.name))
    elif args.command == "make-operator":
        asyncio.run(make_operator(args.email))
    elif args.command == "seed-demo":
        asyncio.run(seed_demo())


if __name__ == "__main__":
    main()
