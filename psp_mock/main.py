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
from fastapi import BackgroundTasks, FastAPI, Form, Header, HTTPException, Query
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

DECLINED_CARD = "4000000000000002"

TEXTS = {
    "en": {
        "badge": "Learning project · no real money",
        "title": "Test bank",
        "for": "Top-up of a Monetka wallet",
        "card": "Card number",
        "expiry": "Expiry",
        "cvc": "CVC",
        "pay": "Pay",
        "cancel": "Cancel",
        "cards": "Test cards",
        "ok": "payment succeeds",
        "declined": "bank declines",
        "note": "Nothing is charged: this page stands in for a bank in local runs.",
    },
    "uk": {
        "badge": "Навчальний проєкт · гроші не справжні",
        "title": "Тестовий банк",
        "for": "Поповнення гаманця Monetka",
        "card": "Номер картки",
        "expiry": "Термін дії",
        "cvc": "CVC",
        "pay": "Оплатити",
        "cancel": "Скасувати",
        "cards": "Тестові картки",
        "ok": "оплата проходить",
        "declined": "банк відхиляє",
        "note": "Нічого не списується: ця сторінка замінює банк для локального запуску.",
    },
}

PAGE = """<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ font: 16px/1.5 ui-monospace, Menlo, Consolas, monospace; background: #f3efe6;
         color: #1d1b16; display: grid; place-items: center; min-height: 100vh; margin: 0;
         padding: 16px; box-sizing: border-box; }}
  main {{ background: #fffdf8; border: 2px solid #1d1b16; box-shadow: 6px 6px 0 #1d1b16;
          padding: 28px; width: min(400px, 100%); box-sizing: border-box; }}
  .badge {{ display: inline-block; font-size: 12px; font-weight: 700; padding: 4px 8px;
            border: 2px dashed #1d1b16; background: #f6e6c8; margin: 0 0 14px; }}
  h1 {{ font-size: 14px; letter-spacing: .12em; text-transform: uppercase; margin: 0 0 4px; }}
  .for {{ margin: 0 0 4px; color: #5c574c; font-size: 14px; }}
  .sum {{ font-size: 32px; font-weight: 700; margin: 0 0 20px; }}
  label {{ display: block; font-size: 13px; font-weight: 700; margin-bottom: 4px; }}
  input {{ width: 100%; box-sizing: border-box; font: inherit; padding: 10px;
           border: 2px solid #1d1b16; background: #fff; margin-bottom: 14px; }}
  .two {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
  .row {{ display: flex; gap: 10px; }}
  button {{ flex: 1; font: inherit; font-weight: 700; padding: 12px; cursor: pointer;
            border: 2px solid #1d1b16; box-shadow: 3px 3px 0 #1d1b16; }}
  .pay {{ background: #1f5f3b; color: #fff; }} .cancel {{ background: #fff; color: #1d1b16; }}
  :focus-visible {{ outline: 3px solid #c2410c; outline-offset: 2px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 18px; }}
  caption {{ text-align: left; font-weight: 700; margin-bottom: 4px; }}
  td {{ padding: 4px 0; border-top: 1px dashed #d8cfbb; }}
  p.note {{ font-size: 12px; color: #5c574c; margin: 14px 0 0; }}
</style></head>
<body><main>
  <p class="badge">{badge}</p>
  <h1>{title}</h1>
  <p class="for">{for}</p>
  <p class="sum">{amount} ₴</p>
  <form method="post" action="/checkout/complete">
    <input type="hidden" name="data" value="{data}">
    <input type="hidden" name="signature" value="{signature}">
    <label for="card">{card}</label>
    <input id="card" name="card" value="4242 4242 4242 4242" inputmode="numeric"
           autocomplete="off" pattern="[0-9 ]{{12,23}}" required>
    <div class="two">
      <div><label for="exp">{expiry}</label>
        <input id="exp" value="12/30" autocomplete="off" required></div>
      <div><label for="cvc">{cvc}</label>
        <input id="cvc" value="123" inputmode="numeric" autocomplete="off" required></div>
    </div>
    <div class="row">
      <button class="pay" name="outcome" value="pay">{pay}</button>
      <button class="cancel" name="outcome" value="cancel" formnovalidate>{cancel}</button>
    </div>
  </form>
  <table>
    <caption>{cards}</caption>
    <tr><td>4242 4242 4242 4242</td><td>{ok}</td></tr>
    <tr><td>4000 0000 0000 0002</td><td>{declined}</td></tr>
  </table>
  <p class="note">{note}</p>
</main></body></html>"""


def language(accept_language: str | None) -> str:
    return "uk" if (accept_language or "").lower().startswith(("uk", "ru")) else "en"


def verified(data: str, signature: str) -> dict[str, Any]:
    params = decode_checkout(settings.secret, data, signature)
    if params is None:
        raise HTTPException(400, "Bad signature")
    return params


@app.get("/checkout", response_class=HTMLResponse)
async def checkout(
    data: Annotated[str, Query()],
    signature: Annotated[str, Query()],
    accept_language: Annotated[str | None, Header()] = None,
) -> str:
    params = verified(data, signature)
    lang = language(accept_language)
    return PAGE.format(
        lang=lang,
        amount=f"{params['amount'] / 100:.2f}",
        data=html.escape(data),
        signature=html.escape(signature),
        **TEXTS[lang],
    )


def outcome_of(action: str, card: str) -> Literal["succeeded", "failed"]:
    """Like Stripe test cards: one number always fails, any other one pays."""
    if action == "cancel" or card.replace(" ", "") == DECLINED_CARD:
        return "failed"
    return "succeeded"


@app.post("/checkout/complete")
async def complete(
    background: BackgroundTasks,
    data: Annotated[str, Form()],
    signature: Annotated[str, Form()],
    outcome: Annotated[Literal["pay", "cancel"], Form()],
    card: Annotated[str, Form()] = "4242",
) -> RedirectResponse:
    params = verified(data, signature)
    event = {
        "event_id": f"evt_{uuid4().hex}",
        "deposit_id": params["deposit_id"],
        "status": outcome_of(outcome, card),
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
