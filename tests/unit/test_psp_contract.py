import time

import pytest

from app.domain.errors import InvalidSignature
from app.integrations import psp
from psp_mock import signing
from psp_mock.main import outcome_of

SECRET = "test-secret"


def test_provider_reads_what_we_sign() -> None:
    data, signature = psp.encode_checkout(SECRET, {"deposit_id": "d1", "amount": 500})
    assert signing.decode_checkout(SECRET, data, signature) == {"deposit_id": "d1", "amount": 500}


def test_provider_rejects_a_changed_amount() -> None:
    forged, _ = psp.encode_checkout("attacker", {"amount": 1})
    _, signature = psp.encode_checkout(SECRET, {"amount": 500})
    assert signing.decode_checkout(SECRET, forged, signature) is None


def test_we_accept_what_the_provider_signs() -> None:
    timestamp = str(int(time.time()))
    signature = signing.sign(SECRET, timestamp.encode() + b".{}")
    psp.verify_webhook(SECRET, b"{}", timestamp, signature, time.time(), 300)


def test_old_or_tampered_webhooks_are_rejected() -> None:
    old = str(int(time.time()) - 3600)
    signature = signing.sign(SECRET, old.encode() + b".{}")
    with pytest.raises(InvalidSignature):
        psp.verify_webhook(SECRET, b"{}", old, signature, time.time(), 300)
    with pytest.raises(InvalidSignature):
        psp.verify_webhook(SECRET, b"{ }", old, signature, int(old), 300)


def test_test_cards_decide_the_outcome() -> None:
    assert outcome_of("pay", "4242 4242 4242 4242") == "succeeded"
    assert outcome_of("pay", "4000 0000 0000 0002") == "failed"
    assert outcome_of("cancel", "4242 4242 4242 4242") == "failed"
