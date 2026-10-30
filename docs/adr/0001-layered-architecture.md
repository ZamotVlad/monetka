# ADR-0001. Layered architecture

**Status:** accepted

## Context

Monetka moves money. The rules about money (amounts are never negative, every movement
has two sides that sum to zero, a payment cannot be captured twice) matter more than any
framework detail, and they must be testable without a database or HTTP.

## Decision

The code is split into layers. Each layer depends only on the ones below it.

| Layer | Package | Responsibility |
| --- | --- | --- |
| API | `app/api` | HTTP: routes, request and response schemas, mapping errors to status codes |
| Services | `app/services` | Use cases. Own the transaction: only a service commits |
| Domain | `app/domain` | Money, ledger and payment rules. Imports no framework |
| Repositories | `app/repositories` | Queries. They flush, but never commit |
| Database | `app/db` | ORM models, engine, session factory, unit of work |

Infrastructure (engine, Redis client, later the Kafka producer) is created once in the
FastAPI lifespan and reaches handlers through dependencies, not module-level globals.

## Consequences

- Domain rules get fast unit tests with no database, network or event loop setup.
- A use case reads top to bottom in one service method, and its transaction boundary is
  visible in one place.
- More files than a single-module app. That is the price for keeping money rules isolated.
