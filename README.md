# Monetka

A digital wallet with shop payments on a double-entry ledger.

> **Learning project.** No real money moves anywhere: the card provider is a mock and
> every balance is play money.

**Live demo:** https://zamotvlad.github.io/monetka/ (runs in the browser with a mock backend)

![Wallet](docs/screenshots/wallet.png)

## Features

- Top-ups through a card provider, transfers by email, withdrawals
- Shop payments in two steps: reserve, then charge or release (auto-release after 7 days)
- Operator panel with the raw journal and reconciliation
- Live balance updates, Ukrainian and English UI, light and dark theme

## How money stays correct

| Risk | Solution |
| --- | --- |
| Money created or lost | Double-entry ledger, postings sum to zero, integer kopiyky |
| Retry charges twice | `Idempotency-Key` stored in the same transaction as the operation |
| Parallel requests overdraw | `SELECT ... FOR UPDATE` in id order, `CHECK` constraint as a backstop |
| Duplicate or forged webhooks | HMAC with timestamp, event dedupe, final states never change |
| Events out of sync with data | Transactional outbox relayed to Kafka |
| Silent drift | Scheduled reconciliation of every balance against its entries |

Details in [docs/adr](docs/adr).

## Run

```bash
docker compose up --build -d
docker compose exec api python -m app.cli seed-demo
```

Open http://localhost:8000 and sign in as `olena@monetka.demo` / `demo-password`.
The header links the wallet, the demo coffee shop (its API key is filled in) and the
operator panel (`ops@monetka.demo`). The wallet has a test money button.
API docs at `/docs`, Grafana on port 3000.

## Test

```bash
uv sync
uv run pytest
```

118 tests, integration ones against real PostgreSQL via testcontainers: 100 parallel
withdrawals, idempotent retries, capture/void races, webhook replays, outbox failures,
plus a Hypothesis property test of the ledger. Ruff and strict mypy in CI.

Load test ([Locust](loadtest/locustfile.py)), 100 users on one machine: 7 006 requests,
0 errors, balance read p50 42 ms, transfer p50 110 ms, books balanced after the run.

## Stack

Python 3.12, FastAPI, SQLAlchemy 2.0 async, PostgreSQL, Alembic, Redis, Kafka (Redpanda),
S3 (LocalStack), Prometheus, Grafana, Docker Compose, GitHub Actions.
Frontend: HTML, CSS and JavaScript modules, no framework.
