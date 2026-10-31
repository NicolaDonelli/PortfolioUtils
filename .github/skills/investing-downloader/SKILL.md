---
name: investing-downloader
description: Design, implement, debug or extend the PortfolioUtils download subpackage that logs in to www.investing.com with the owner's credentials, resolves ETFs (ISIN or ticker) to investing.com instruments, downloads historical prices and stores them as CSV files in data/. Use for any task about downloading, updating or storing ETF price history, investing.com authentication, Cloudflare blocks or changed response formats.
argument-hint: "[task, e.g. 'implement instrument search' or 'debug 403 on historical data']"
---
# investing.com downloader

## Ground rules

- Credentials only from `INVESTING_EMAIL` / `INVESTING_PASSWORD` through
  `portfolio_utils.settings`. Never read `.env`, never print or log credentials, cookies or
  tokens, never type credentials into a browser tool or a terminal command.
- investing.com has no public API: the endpoints are undocumented and can change. Respect
  the site's terms of use, download for personal use only, throttle requests and never
  parallelise.
- Tests never call investing.com (see the `write-tests` skill).

## Procedure

1. **Read the current state**: `portfolio_utils/download/`, `portfolio_utils/settings.py`,
   `tests/download/` and [the design reference](./reference/design.md).
2. **Explore before coding** (only when an endpoint or response format is unknown or broke):
   - Use the Playwright MCP server on **public pages** (instrument search, the
     "Historical Data" page of an ETF) to observe the network requests the page makes
     (`browser_network_requests`). Note URL, method, query parameters, required headers
     and the JSON shape.
   - Do not log in through the browser tool. If a flow requires authentication, describe
     the observed login request shape to the owner and implement it in code, reading the
     credentials from settings.
   - Save one anonymised example response per scenario in `tests/resources/investing/`.
3. **Implement in layers**, smallest first, each with tests:
   1. `storage.py` – CSV schema, read, merge, atomic write ([schema](./reference/csv-schema.md)).
   2. `client.py` – session, headers, timeouts, retries, throttling, login.
   3. `instruments.py` – search by ISIN/ticker, disambiguate by exchange and currency.
   4. `historical.py` – request historical prices in date windows, parse, validate.
   5. Public facade in `download/__init__.py`, e.g.
      `download_history(isin: str, start: date | None = None, *, data_dir: Path | None = None) -> Path`.
4. **Verify**: unit tests with fakes, then `quality-gate`. Optionally run one manual smoke
   download of a single ETF and report row count and date range (not the data itself).

## Troubleshooting

| Symptom | Likely cause / action |
|---|---|
| HTTP 403 with an HTML challenge page | Cloudflare bot protection: use `curl_cffi` with browser impersonation, keep a single session, slow down. |
| HTTP 429 | Too many requests: increase throttling, back off exponentially. |
| JSON keys missing or renamed | Endpoint changed: re-run step 2, update parser, fixtures and the verification date in the module docstring. |
| Login succeeds but data empty | Wrong instrument id / exchange: check the ISIN resolution and the currency. |
| Gaps in history | Holidays or long ranges truncated by the server: split the range in yearly windows. |
