# Download subpackage – reference design

> Endpoints below are **hypotheses to verify** with the Playwright MCP server before coding.
> They have been used by community projects in the past and may have changed.

| Purpose | Candidate request (verify!) |
|---|---|
| Instrument search | `GET https://api.investing.com/api/search/v2/search?q=<ISIN or ticker>` |
| Historical prices | `GET https://api.investing.com/api/financialdata/historical/<instrument_id>?start-date=YYYY-MM-DD&end-date=YYYY-MM-DD&time-frame=Daily&add-missing-rows=false` |
| Typical extra header | `domain-id: www` |

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
