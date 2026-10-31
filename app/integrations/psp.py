"""The contract with the card payment provider, in the style of LiqPay and Stripe.

Checkout: we send the user to the provider with base64 JSON `data` and an HMAC `signature`
of it, so the user cannot change the amount in the URL.

Webhook: the provider calls us back with the result. It signs "<timestamp>.<raw body>".
The timestamp stops an attacker from replaying an old, validly signed request.
"""

import base64
import hashlib
import hmac
import json
from typing import Any

from app.domain.errors import InvalidSignature


def sign(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def encode_checkout(secret: str, params: dict[str, Any]) -> tuple[str, str]:
    data = base64.urlsafe_b64encode(json.dumps(params).encode()).decode()
    return data, sign(secret, data.encode())


def verify_webhook(
    secret: str, body: bytes, timestamp: str, signature: str, now: float, tolerance: int
) -> None:
    expected = sign(secret, timestamp.encode() + b"." + body)
    # compare_digest takes the same time whatever the input, so timing leaks nothing
    if not hmac.compare_digest(expected, signature):
        raise InvalidSignature("Webhook signature does not match")
    try:
        sent_at = int(timestamp)
    except ValueError as error:
        raise InvalidSignature("Bad webhook timestamp") from error
    if abs(now - sent_at) > tolerance:
        raise InvalidSignature("Webhook is too old")
