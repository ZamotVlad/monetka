# ADR-0003. Idempotency keys and row locks

**Status:** accepted

## Context

Mobile networks drop responses. A client that retries a transfer must not send the money
twice. And two requests that spend from one wallet at the same moment must not both see
the old balance.

## Decision

**Idempotency.** Money-moving POSTs require an `Idempotency-Key` header. The key is stored
in PostgreSQL (`INSERT ... ON CONFLICT DO NOTHING`) in the same transaction as the
operation, together with a hash of the request and the response. A retry with the same key
gets the stored response and an `Idempotent-Replayed: true` header; the same key with a
different body gets `422 idempotency_conflict`. If two copies arrive at once, the second
INSERT waits on the unique index until the first commits, then replays its answer.
A failed operation rolls back its key, so the client can retry.

PostgreSQL rather than Redis: the key and the money must commit atomically, and Redis is
not part of that transaction.

**Locking.** The ledger service locks every account a transaction touches with
`SELECT ... FOR UPDATE`, ordered by id. Ordering means A→B and B→A transfers lock in the
same order and queue instead of deadlocking. Payments are locked the same way, so capture,
void and expiry cannot both succeed.

## Consequences

- Tests prove it: 100 parallel withdrawals from a balance that fits 50 give exactly 50
  successes and a zero balance; 20 parallel copies of one request move money once.
- Pessimistic locks serialize spending from one wallet. That is the desired behaviour for
  money; throughput across different wallets is unaffected.
