# ADR-0002. Double-entry ledger with cached balances

**Status:** accepted

## Context

A wallet that stores only `balance` and runs `UPDATE balance = balance - 100` cannot
answer "where did this money come from?", and a bug that changes one balance goes
unnoticed.

## Decision

Every movement is a ledger transaction with at least two entries (postings). An entry
adds a signed amount to one account; the entries of a transaction sum to zero.
Accounts: a wallet and a hold (reserve) account per user, one account per merchant and a
system account for the card provider. The provider account is allowed to go negative: its
balance mirrors the real money the provider holds for us.

Amounts are integers in minor units (`BIGINT` kopiyky, a `Money` value object in code).
Never `float`.

`accounts.balance` is kept as a cache of the sum of entries, updated in the same
transaction as the entries, so reading a balance is one row. A `CHECK` constraint keeps
non-system balances at zero or above even if the code is wrong.

## Consequences

- Reconciliation can prove the books: each balance equals its entries, each transaction
  sums to zero, all balances together sum to zero.
- Holds are ordinary transfers to a hold account, so "available" and "reserved" fall out
  of the same model with no special cases.
- The provider account is one hot row: every top-up and withdrawal locks it. Fine at this
  scale; at high volume it would be split into several shard accounts.
