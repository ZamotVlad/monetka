"""A pretend card provider for local runs: a checkout page and signed webhooks.

Run: uvicorn psp_mock.main:app --port 8001
"""

import asyncio
import html
import json
import logging
import time
from typing import Annotated, Any, Literal
from uuid import uuid4

import httpx
from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic_settings import BaseSettings, SettingsConfigDict

from psp_mock.signing import decode_checkout, sign

logger = logging.getLogger("psp_mock")


class PspSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PSP_")

    secret: str = "local-dev-psp-secret-change-me-in-production"
    # Real providers retry and sometimes send twice; doing it on purpose shows the dedupe
    duplicate_webhooks: bool = True
    webhook_delay_seconds: float = 1.5


settings = PspSettings()
app = FastAPI(title="Monetka PSP mock", docs_url=None, redoc_url=None)

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Card payment</title>
<style>
  body {{ font: 16px/1.5 ui-monospace, Menlo, Consolas, monospace; background: #f3efe6;
         color: #1d1b16; display: grid; place-items: center; min-height: 100vh; margin: 0; }}
  main {{ background: #fffdf8; border: 2px solid #1d1b16; box-shadow: 6px 6px 0 #1d1b16;
          padding: 28px; width: min(360px, calc(100vw - 32px)); box-sizing: border-box; }}
  h1 {{ font-size: 14px; letter-spacing: .12em; text-transform: uppercase; margin: 0 0 16px; }}
  .sum {{ font-size: 32px; font-weight: 700; margin: 0 0 20px; }}
  label {{ display: block; font-size: 13px; margin-bottom: 4px; }}
  input {{ width: 100%; box-sizing: border-box; font: inherit; padding: 10px;
           border: 2px solid #1d1b16; background: #fff; margin-bottom: 16px; }}
  .row {{ display: flex; gap: 10px; }}
  button {{ flex: 1; font: inherit; font-weight: 700; padding: 12px; cursor: pointer;
            border: 2px solid #1d1b16; box-shadow: 3px 3px 0 #1d1b16; }}
  .pay {{ background: #2f6f4f; color: #fff; }} .decline {{ background: #fff; }}
  button:focus-visible {{ outline: 3px solid #c2410c; outline-offset: 2px; }}
  .badge {{ display: inline-block; font-size: 12px; font-weight: 700; padding: 4px 8px;
            border: 2px dashed #1d1b16; background: #f6e6c8; margin: 0 0 14px; }}
  p.note {{ font-size: 12px; color: #5c574c; margin: 16px 0 0; }}
</style></head>
<body><main>
  <p class="badge">Learning project · no real money</p>
  <h1>Test card provider</h1>
  <p class="sum">{amount} ₴</p>
  <form method="post" action="/checkout/complete">
    <input type="hidden" name="data" value="{data}">
    <input type="hidden" name="signature" value="{signature}">
    <label for="card">Card number</label>
    <input id="card" name="card" value="4242 4242 4242 4242" inputmode="numeric"
           autocomplete="off" pattern="[0-9 ]{{16,19}}">
    <div class="row">
      <button class="pay" name="outcome" value="succeeded">Pay</button>
      <button class="decline" name="outcome" value="failed">Decline</button>
    </div>
  </form>
  <p class="note">Nothing is charged: this page stands in for a bank in local runs.
  Any card number works.</p>
</main></body></html>"""


def verified(data: str, signature: str) -> dict[str, Any]:
    params = decode_checkout(settings.secret, data, signature)
    if params is None:
        raise HTTPException(400, "Bad signature")
    return params


@app.get("/checkout", response_class=HTMLResponse)
async def checkout(data: Annotated[str, Query()], signature: Annotated[str, Query()]) -> str:
    params = verified(data, signature)
    return PAGE.format(
        amount=f"{params['amount'] / 100:.2f}",
        data=html.escape(data),
        signature=html.escape(signature),
    )


@app.post("/checkout/complete")
async def complete(
    background: BackgroundTasks,
    data: Annotated[str, Form()],
    signature: Annotated[str, Form()],
    outcome: Annotated[Literal["succeeded", "failed"], Form()],
    card: Annotated[str, Form()] = "4242",
) -> RedirectResponse:
    params = verified(data, signature)
    event = {
        "event_id": f"evt_{uuid4().hex}",
        "deposit_id": params["deposit_id"],
        "status": outcome,
        "amount": params["amount"],
        "card_last4": card.replace(" ", "")[-4:],
    }
    background.add_task(deliver, params["callback_url"], event)
    return RedirectResponse(params["return_url"], status_code=303)


async def deliver(url: str, event: dict[str, Any]) -> None:
    await asyncio.sleep(settings.webhook_delay_seconds)
    copies = 2 if settings.duplicate_webhooks else 1
    async with httpx.AsyncClient(timeout=5) as client:
        for _ in range(copies):
            for attempt in range(5):
                body = json.dumps(event).encode()
                timestamp = str(int(time.time()))
                headers = {
                    "Content-Type": "application/json",
                    "X-Psp-Timestamp": timestamp,
                    "X-Psp-Signature": sign(settings.secret, timestamp.encode() + b"." + body),
                }
                try:
                    response = await client.post(url, content=body, headers=headers)
                    logger.info("webhook %s -> %s", event["event_id"], response.status_code)
                    if response.status_code < 500:
                        break
                except httpx.HTTPError as error:
                    logger.warning("webhook %s failed: %s", event["event_id"], error)
                await asyncio.sleep(2**attempt)
