---
name: 'investing.com downloader'
description: 'Rules for the download subpackage: credential handling, HTTP client, throttling, parsing and CSV storage in data/. Use when working on downloading ETF prices from investing.com.'
applyTo: 'portfolio_utils/download/**/*.py,tests/download/**/*.py'
---
# `portfolio_utils.download`

## Credentials
- Read `INVESTING_EMAIL` / `INVESTING_PASSWORD` only through `portfolio_utils.settings`
  (environment first, then the git-ignored `.env`). Store the password as
  `pydantic.SecretStr` or in a class whose `__repr__` masks it.
- Never log request bodies, cookies, tokens or headers of authenticated requests. Log the
  URL path, status code and elapsed time only.
- Raise `AuthenticationError` with a generic message on login failure (no echo of input).

## HTTP client
- One `InvestingClient` class owns the session; the session object is injected
  (constructor argument) so tests can pass a fake.
- Always set explicit timeouts; retry only idempotent GETs on 429 / 5xx / connection errors
  with exponential backoff and jitter, maximum 3 attempts.
- Throttle: at least 1–2 seconds between requests, no concurrency.
- investing.com sits behind Cloudflare: plain `requests` is often blocked. Prefer
  `curl_cffi` with browser impersonation. Keep the transport isolated so it can be replaced.
- Every undocumented endpoint used must be described in the module docstring with the date
  it was last verified and an example of the response shape (stored in `tests/resources/`).

## Parsing and storage
- Validate responses explicitly (expected keys, types, non-empty) and raise
  `UnexpectedResponseError` with context when the format changes.
- CSV schema (single source of truth in `storage.py`): columns
  `date,open,high,low,close,volume`, ISO dates `YYYY-MM-DD`, ascending, unique, `.` as
  decimal separator, UTF-8, no index column.
- File name: `data/<instrument_slug>.csv` plus a sidecar `data/<instrument_slug>.meta.json`
  (investing.com id, ISIN, symbol, exchange, currency, last download timestamp).
- Incremental updates: read the last stored date, download only newer rows, merge, drop
  duplicates keeping the newest value, sort, then write atomically (temporary file +
  `Path.replace`).
- Create `data/` if missing; never delete existing files.
