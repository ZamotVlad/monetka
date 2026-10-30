# Monetka

A digital wallet with merchant payments, built on a double-entry ledger.
Users top up, send money to each other, pay in shops and withdraw.
Shop payments work in two steps: the amount is held first and captured or released later.

> Work in progress. The project is built in stages, see [Roadmap](#roadmap).

## Roadmap

- [x] **Stage 0.** Project skeleton: app factory, settings, health probes, Docker, CI
- [ ] **Stage 1.** Ledger core: accounts, double-entry postings, `Money` value object, auth
- [ ] **Stage 2.** Top-ups, transfers and withdrawals with idempotency keys and row locks
- [ ] **Stage 3.** Merchant payments: hold, capture, release, automatic expiry
- [ ] **Stage 4.** Payment provider webhooks with signatures and duplicate protection
- [ ] **Stage 5.** Transactional outbox and Kafka events, balance reconciliation
- [ ] **Stage 6.** Web app for users and an operator panel
- [ ] **Stage 7.** Metrics, load tests and monthly statements

## Stack

Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async) with asyncpg, Alembic,
PostgreSQL 16, Redis, uv, pytest, Ruff, mypy (strict), Docker Compose, GitHub Actions.

## Getting started

Requirements: Docker with Compose.

```bash
docker compose up --build
curl http://localhost:8000/api/v1/health/ready
```

Interactive API docs: http://localhost:8000/docs

### Running without Docker

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), PostgreSQL and Redis
(for example, `docker compose up postgres redis`).

```bash
uv sync
cp .env.example .env
uv run uvicorn app.main:app --reload
```

## Health checks

| Endpoint | Meaning |
| --- | --- |
| `GET /api/v1/health/live` | The process is running. Does not check dependencies |
| `GET /api/v1/health/ready` | PostgreSQL and Redis answer. Returns `503` if one of them is down |

Liveness and readiness are separate so an orchestrator restarts the app only when the app
itself is stuck, not when the database blips. Each readiness probe has its own timeout,
so a hung dependency cannot hang the check.

## Development

```bash
uv run ruff check .
uv run ruff format .
uv run mypy app tests
uv run pytest
```

`pre-commit install` runs the same checks before each commit.

## Architecture decisions

Key decisions are recorded in [docs/adr](docs/adr):

- [ADR-0001. Layered architecture](docs/adr/0001-layered-architecture.md)
