# PortfolioUtils – project instructions for Copilot

## What this project is

`portfolio-utils` (import name `portfolio_utils`) is a strictly typed Python 3.13 library that:

1. **downloads** historical ETF prices from www.investing.com using the owner's personal account and stores them as CSV files in `data/` (subpackage `portfolio_utils.download`);
2. **analyses** those time series to build an investment portfolio from historical performance (subpackage `portfolio_utils.analysis`).

It is a personal project: correctness, reproducibility and protection of the owner's credentials matter more than speed of delivery.

## Environment and commands

- Development happens inside the Dev Container (`.devcontainer/devcontainer.json`: Debian, Python 3.13, `uv`). The shell is bash and the virtual environment is `.venv`.
- GNU Make orchestrates everything. Always use the Make targets instead of calling the tools ad hoc, because the targets keep `requirements/*.txt` and the venv in sync:
  - `make setup_dev` – compiles `requirements/requirements_dev.txt` from `pyproject.toml` with `uv pip compile` and syncs the venv with `uv pip sync`.
  - `make format` / `make lint` – auto-fix with ruff.
  - `make check_format`, `make check_lint` (ruff + pydoclint), `make mypy`, `make tests`, `make licensecheck`.
  - `make checks` – all of the above. This is exactly what the git **pre-push** hook and the CI workflow run, so it is the real gate.
  - `make docs` – Sphinx HTML documentation (also run in CI).
- `requirements/*.txt` are generated and git-ignored: never edit them by hand. These files are required just to keep track of the complete set of dependencies available when the last local `make checks` command successfully run. Actual package dependencies are declared only in `pyproject.toml` (`[project].dependencies` for runtime, `[dependency-groups].dev` for tooling). Use the `add-dependency` skill.
- The version comes from git tags through `setuptools_scm`: never hard-code a version.

## Definition of done for every code change

1. `make checks` passes: ruff format, ruff lint, pydoclint (Sphinx style), strict mypy on `portfolio_utils` **and** `tests`, licensecheck, pytest with branch coverage ≥ 95 %.
2. New or changed behaviour is covered by tests in `tests/`, mirroring the package layout.
3. Every public module, class and function has a Sphinx-style docstring accepted by pydoclint.
4. No suppression comments (`# noqa`, `# type: ignore`, `# pragma: no cover`) unless truly unavoidable; when used they must be specific (`# type: ignore[import-untyped]`, `# noqa: S113`) and followed by a short reason.
5. Never lower thresholds or disable rules in `pyproject.toml`, `Makefile`, `.pre-commit-config.yaml` or `.commitlintrc.yaml` to make a check pass. Fix the code, or stop and ask the owner.

## Coding standards (rules the tools do not fully explain)

- **Typing**: mypy runs with `disallow_untyped_defs`, `disallow_untyped_calls`,`disallow_any_generics`, `warn_return_any` and also checks the tests. Annotate every function, tests included (`-> None`). Always parametrise generics (`list[str]`, `dict[str, float]`). Use `collections.abc` types for parameters (`Sequence`, `Mapping`, `Iterable`) and concrete types for return values. pandas is typed through `pandas-stubs`.
- **Docstrings**: Sphinx/reST fields (`:param name:`, `:return:`, `:raises ExcType:`). Types live in the signature, never in the docstring (pydoclint `arg-type-hints-in-docstring = false`). Examples in docstrings must be valid doctests because pytest runs with `--doctest-modules`.
- **Complexity**: keep functions small and single-purpose (project target: McCabe ≤ 7).
- **Formatting**: ruff format, line length 88, double quotes. Do not fight the formatter.
- Use `pathlib.Path`, `logging` (`logger = logging.getLogger(__name__)` per module) and never `print` in library code.
- Prefer immutable value objects (`@dataclass(frozen=True, slots=True)`), `Final` constants and `Literal` types over magic strings.
- Raise exceptions from the package hierarchy (`PortfolioUtilsError` and subclasses) with actionable messages; never swallow exceptions silently.

## Target architecture

```
portfolio_utils/
├── __init__.py            # version only
├── settings.py            # credentials and paths from env / .env (never hard-coded)
├── exceptions.py          # PortfolioUtilsError hierarchy
├── download/
│   ├── __init__.py        # public API (__all__)
│   ├── client.py          # HTTP session, login, retries, throttling
│   ├── instruments.py     # resolve ETF (ISIN / ticker) -> investing.com instrument id
│   ├── historical.py      # fetch and parse historical prices
│   └── storage.py         # CSV schema, atomic write, incremental merge in data/
└── analysis/
    ├── __init__.py        # public API (__all__)
    ├── loading.py         # load CSVs from data/ into aligned price panels
    ├── returns.py         # simple / log returns, resampling
    ├── metrics.py         # CAGR, volatility, Sharpe, Sortino, drawdown, ...
    ├── optimization.py    # portfolio weights (min variance, max Sharpe, risk parity, ...)
    └── backtest.py        # rebalancing back-tests without look-ahead bias
```

The two subpackages communicate only through the CSV files in `data/` and the schema
defined in `download/storage.py`. `analysis` must never import from `download`.

## Security and credentials

- investing.com credentials are read only from the environment variables
  `INVESTING_EMAIL` and `INVESTING_PASSWORD` (optionally loaded from the git-ignored `.env`). Never print, log, echo, commit or copy them into tests, fixtures, docstrings, terminal commands or chat.
- Never open, read or display `.env`. Document variables in `.env.example` (no real values).
- `detect-secrets` runs at pre-commit: use obviously fake values in tests and mark them with `# pragma: allowlist secret`.
- Tests never touch the network: inject fake HTTP sessions and use small recorded fixtures in `tests/resources/`.
- `data/` is git-ignored and holds the owner's downloaded data. Do not delete or rewrite files there; tests write into `tmp_path`.
- Access investing.com sparingly (throttling, no parallel scraping) and for personal use.

## Git

- Conventional commits are enforced by commitlint: `<type>(<optional scope>): <description>.` with type in `fix, feat, doc, perf, refactor, style, test, chore`, written in English, description ending with a period, blank line before body and footers. See the `conventional-commit` skill.
- Never use `--no-verify`, never skip or uninstall the pre-commit hooks.
