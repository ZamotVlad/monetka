import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from uuid import UUID

import bcrypt
import jwt

from app.domain.errors import InvalidCredentials

JWT_ALGORITHM = "HS256"


def hash_password(password: str, rounds: int) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


@lru_cache
def dummy_hash(rounds: int) -> str:
    # Checked when the email is unknown, so "no such user" takes as long as "wrong password"
    # and response time does not reveal which emails are registered
    return hash_password(secrets.token_hex(8), rounds)


def create_access_token(user_id: UUID, secret: str, ttl_minutes: int) -> str:
    now = datetime.now(UTC)
    claims = {"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=ttl_minutes)}
    return jwt.encode(claims, secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, secret: str) -> UUID:
    try:
        # algorithms is pinned, otherwise a token signed with "none" could pass
        claims = jwt.decode(
            token, secret, algorithms=[JWT_ALGORITHM], options={"require": ["exp", "sub"]}
        )
        return UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError) as error:
        raise InvalidCredentials("Invalid or expired token") from error


def generate_api_key() -> str:
    return "mk_" + secrets.token_urlsafe(32)


def hash_api_key(api_key: str) -> str:
    # A random 256-bit key needs no slow hash: there is nothing to brute-force
    return hashlib.sha256(api_key.encode()).hexdigest()
