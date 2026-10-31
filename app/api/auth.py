from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, SettingsDep, UoW
from app.api.rate_limit import auth_limit
from app.api.schemas import Credentials, Token, UserOut
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED, dependencies=[Depends(auth_limit)])
async def register(body: Credentials, uow: UoW, settings: SettingsDep) -> UserOut:
    user = await AuthService(uow, settings).register(body.email, body.password)
    await uow.commit()
    return UserOut.model_validate(user)


@router.post("/login", dependencies=[Depends(auth_limit)])
async def login(body: Credentials, uow: UoW, settings: SettingsDep) -> Token:
    token = await AuthService(uow, settings).login(body.email, body.password)
    return Token(access_token=token)


@router.get("/me")
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
