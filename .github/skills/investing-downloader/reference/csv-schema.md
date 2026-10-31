# CSV schema for `data/`

File `data/<slug>.csv`, where `<slug>` is lowercase ASCII, e.g. `ishares-core-msci-world-ucits-etf-xetra`.

| Column | Type | Notes |
|---|---|---|
| `date` | ISO date `YYYY-MM-DD` | trading date, ascending, unique |
| `open` | float | `.` decimal separator |
| `high` | float | |
| `low` | float | |
| `close` | float | price used for returns |
| `volume` | int, may be empty | |

- UTF-8, comma separated, header row, no index column, `\n` line endings.
- Missing values are empty fields, never `0`.

Sidecar `data/<slug>.meta.json`:

```json
{
  "investing_id": 12345,
  "isin": "IE00B4L5Y983",
  "symbol": "EUNL",
  "name": "iShares Core MSCI World UCITS ETF",
  "exchange": "Xetra",
  "currency": "EUR",
  "distribution": "accumulating",
  "last_download_utc": "2026-10-31T10:00:00Z",
  "schema_version": 1
}
```
