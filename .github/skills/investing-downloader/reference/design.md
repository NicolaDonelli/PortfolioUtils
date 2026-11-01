# Download subpackage – reference design

> Verified public behavior as of 2026-10-31 with `curl_cffi` GET requests. This remains
> undocumented site behavior and may change; catalog completeness is not guaranteed.

| Purpose | Observed public request (2026-10-31) |
|---|---|
| Public ETF index | `GET https://www.investing.com/etfs/`; root links expose category pages. |
| ETF categories | `GET https://www.investing.com/etfs/{usa-etfs,world-etfs,major-etfs,cannabis-etfs}`; rows expose IDs, names, symbols, and detail links. |
| ETF detail | `GET https://www.investing.com/etfs/{slug}`; `__NEXT_DATA__` identifies `instrument_id` and type. |
| Historical prices | `GET https://api.investing.com/api/financialdata/historical/<instrument_id>` with `start-date`, `end-date`, `time-frame=Daily`, `add-missing-rows=false`; `domain-id: www`. |

No separate search endpoint is used. Ticker resolution scans root-linked category
tables. The observed root exposed four categories, with 1000 USA, 708 World, 37 Major,
and 12 Cannabis rows; no pagination links appeared in those responses. This does not
establish that the site catalog is exhaustive. A wide historical query returned at
most 4999 earliest rows, so retrieval continues from the latest returned date plus
one day. The adapter uses one public `curl_cffi` session and at least 1.5 seconds
between request starts; it does not log in.

## Settings

```python
class InvestingSettings(BaseSettings):  # pydantic-settings
    """Credentials and paths read from the environment or the git-ignored .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="INVESTING_", extra="ignore")

    email: str
    password: SecretStr
```

## Client

```python
class HttpSession(Protocol):
    """Minimal protocol implemented by curl_cffi sessions and by test fakes."""

    def get(self, url: str, *, params: Mapping[str, str] | None = ..., timeout: float = ...) -> HttpResponse: ...
    def post(self, url: str, *, data: Mapping[str, str] | None = ..., timeout: float = ...) -> HttpResponse: ...


@dataclass(slots=True)
class InvestingClient:
    """Throttled, retrying client for investing.com."""

    session: HttpSession
    min_interval_s: float = 1.5
    max_retries: int = 3
    timeout_s: float = 30.0
    sleep: Callable[[float], None] = time.sleep  # injectable for tests
    clock: Callable[[], float] = time.monotonic
```

Responsibilities: `login(settings)`, `get_json(url, params)` with throttling, retries on
429/5xx/connection errors (exponential backoff + jitter), status validation and safe logging
(path, status, elapsed time only).

## Exceptions

```
PortfolioUtilsError
└── DownloadError
    ├── AuthenticationError
    ├── InstrumentNotFoundError
    ├── RateLimitedError
    └── UnexpectedResponseError
```

## Flow of `download_history`

1. Resolve ISIN/ticker → `Instrument(id, slug, isin, symbol, exchange, currency)`.
2. Read existing `data/<slug>.csv` (if any) → last stored date.
3. Request missing range in yearly windows, throttled.
4. Parse and validate → DataFrame with the CSV schema.
5. Merge with existing rows, deduplicate (keep newest), sort, write atomically.
6. Write/refresh `data/<slug>.meta.json`. Return the CSV path.
