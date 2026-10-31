# ADR-0005. Frontend in plain HTML, CSS and JavaScript

**Status:** accepted

## Context

The project is about the backend. The interface has to be usable by anyone, look
deliberate, and be fully explainable by its author without a build toolchain.

## Decision

Static pages served by FastAPI: ES modules, no framework, no bundler. One `api.js` wraps
`fetch`, adds the token and, for money operations, an idempotency key that is reused on
network retries. Texts live in one dictionary for Ukrainian and English.

The user never sees debits and credits. The wallet shows "available / reserved / total"
and describes each operation in plain words. The technical journal with debit and credit
columns lives only in the operator panel.

For GitHub Pages, where no backend runs, `demo.js` stands in for the API in the browser
with the same rules in miniature, so the same pages work as a live demo.

## Consequences

- No build step, nothing to keep up to date besides the code itself.
- More manual DOM code than a framework would need; acceptable for four pages.
