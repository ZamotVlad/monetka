"""Load test: sign-up, top-up through a signed webhook, then everyday wallet traffic.

uv sync --extra load
AUTH_RATE_LIMIT_PER_MINUTE=100000 docker compose up -d
uv run locust -f loadtest/locustfile.py --host http://localhost:8000
"""

import json
import os
import random
import time
from uuid import uuid4

from locust import FastHttpUser, between, task

from psp_mock.signing import sign

PSP_SECRET = os.environ.get("PSP_SECRET", "local-dev-psp-secret-change-me-in-production")
PASSWORD = "load-test-password"
emails: list[str] = []


class WalletUser(FastHttpUser):
    wait_time = between(0.5, 1.5)

    def on_start(self) -> None:
        self.email = f"load-{uuid4().hex[:12]}@example.com"
        credentials = {"email": self.email, "password": PASSWORD}
        self.client.post("/api/v1/auth/register", json=credentials)
        token = self.client.post("/api/v1/auth/login", json=credentials).json()["access_token"]
        self.headers = {"Authorization": f"Bearer {token}"}
        self.top_up(1_000_000)
        emails.append(self.email)

    def top_up(self, amount: int) -> None:
        deposit = self.client.post(
            "/api/v1/deposits",
            json={"amount": amount},
            headers=self.headers | {"Idempotency-Key": str(uuid4())},
        ).json()
        # Play the provider: send the signed webhook it would send after a card payment
        body = json.dumps(
            {
                "event_id": f"evt_{uuid4().hex}",
                "deposit_id": deposit["id"],
                "status": "succeeded",
                "amount": amount,
                "card_last4": "4242",
            }
        ).encode()
        timestamp = str(int(time.time()))
        self.client.post(
            "/api/v1/webhooks/psp",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Psp-Timestamp": timestamp,
                "X-Psp-Signature": sign(PSP_SECRET, timestamp.encode() + b"." + body),
            },
        )

    @task(5)
    def balance(self) -> None:
        self.client.get("/api/v1/wallet", headers=self.headers)

    @task(3)
    def history(self) -> None:
        self.client.get("/api/v1/wallet/history?limit=20", headers=self.headers)

    @task(2)
    def transfer(self) -> None:
        others = [email for email in emails if email != self.email]
        if not others:
            return
        self.client.post(
            "/api/v1/transfers",
            json={"to_email": random.choice(others), "amount": 100},
            headers=self.headers | {"Idempotency-Key": str(uuid4())},
        )

    @task(1)
    def withdraw(self) -> None:
        self.client.post(
            "/api/v1/withdrawals",
            json={"amount": 50, "card_last4": "4242"},
            headers=self.headers | {"Idempotency-Key": str(uuid4())},
        )
