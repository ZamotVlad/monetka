"""The provider's half of the contract. Kept apart from app/ on purpose: a real provider
shares a secret with us, never code."""

import base64
import hashlib
import hmac
import json
from typing import Any


def sign(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def decode_checkout(secret: str, data: str, signature: str) -> dict[str, Any] | None:
    if not hmac.compare_digest(sign(secret, data.encode()), signature):
        return None
    params: dict[str, Any] = json.loads(base64.urlsafe_b64decode(data))
    return params
