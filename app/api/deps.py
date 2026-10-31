from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings
from app.db.models import User
from app.db.uow import UnitOfWork
from app.domain.errors import InvalidCredentials, PermissionDenied
from app.security import decode_access_token
from app.services.auth import AuthService


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def get_uow(request: Request) -> AsyncIterator[UnitOfWork]:
    async with UnitOfWork(request.app.state.session_factory) as uow:
        yield uow


SettingsDep = Annotated[Settings, Depends(get_settings)]
UoW = Annotated[UnitOfWork, Depends(get_uow)]

bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    uow: UoW,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    if credentials is None:
        raise InvalidCredentials("Sign in first")
    user_id = decode_access_token(credentials.credentials, settings.jwt_secret)
    return await AuthService(uow, settings).get_user(user_id)


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_operator(user: CurrentUser) -> User:
    if not user.is_operator:
        raise PermissionDenied("Operators only")
    return user


Operator = Annotated[User, Depends(get_operator)]
