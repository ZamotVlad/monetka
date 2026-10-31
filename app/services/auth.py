from uuid import UUID

from anyio import to_thread
from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.db.models import Account, User
from app.db.uow import UnitOfWork
from app.domain.errors import EmailTaken, InvalidCredentials
from app.domain.ledger import AccountKind
from app.security import create_access_token, dummy_hash, hash_password, verify_password


class AuthService:
    def __init__(self, uow: UnitOfWork, settings: Settings) -> None:
        self._uow = uow
        self._settings = settings

    async def register(self, email: str, password: str) -> User:
        email = email.lower()
        if await self._uow.users.by_email(email) is not None:
            raise EmailTaken("This email is already registered")
        # bcrypt is slow on purpose; in a thread it does not freeze the event loop
        password_hash = await to_thread.run_sync(
            hash_password, password, self._settings.bcrypt_rounds
        )
        user = User(email=email, password_hash=password_hash)
        self._uow.users.add(user)
        try:
            await self._uow.session.flush()
        except IntegrityError as error:
            # Two sign-ups with one email at the same moment: the unique index decides
            raise EmailTaken("This email is already registered") from error
        self._uow.accounts.add(Account(kind=AccountKind.WALLET, user_id=user.id))
        self._uow.accounts.add(Account(kind=AccountKind.HOLD, user_id=user.id))
        await self._uow.session.flush()
        return user

    async def login(self, email: str, password: str) -> str:
        user = await self._uow.users.by_email(email)
        password_hash = user.password_hash if user else dummy_hash(self._settings.bcrypt_rounds)
        valid = await to_thread.run_sync(verify_password, password, password_hash)
        if user is None or not valid:
            raise InvalidCredentials("Wrong email or password")
        return create_access_token(
            user.id, self._settings.jwt_secret, self._settings.jwt_ttl_minutes
        )

    async def get_user(self, user_id: UUID) -> User:
        user = await self._uow.users.get(user_id)
        if user is None:
            raise InvalidCredentials("User no longer exists")
        return user
