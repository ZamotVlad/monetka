# ADR-0004. Transactional outbox and Kafka

**Status:** accepted

## Context

Other parts of the system (live updates in the browser, analytics, notifications) need to
know when money moves. Publishing to Kafka inside the request has two failure modes: the
publish succeeds and the transaction rolls back (we announce money that never moved), or
the transaction commits and the publish fails (the event is lost).

## Decision

Services write events to an `outbox` table in the same transaction as the change.
A worker relays unpublished rows to Kafka (Redpanda locally) in id order with
`FOR UPDATE SKIP LOCKED`, then marks them published. Messages are keyed by user id, so one
user's events stay ordered within a partition.

Delivery is at-least-once: if the worker dies after sending and before marking, the batch
is sent again. Consumers must tolerate duplicates. The API's consumer only uses events as
a signal for the browser to reload its data over the WebSocket, so a duplicate is harmless.

## Consequences

- An event exists if and only if its change was committed.
- A few hundred milliseconds of delay between commit and event.
- The outbox table grows; published rows can be deleted by a cleanup job (not needed yet).
