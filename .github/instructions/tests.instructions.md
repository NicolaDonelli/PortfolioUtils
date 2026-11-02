---
name: 'Tests'
description: 'Conventions for offline unit tests and opt-in live integration tests, typing, fixtures, and coverage.'
applyTo: 'tests/**/*.py'
---
# Tests in `tests/`

- Unit tests live under `tests/unit/` and mirror the package:
  `tests/unit/download/test_storage.py` tests
  `portfolio_utils/download/storage.py`. Every test folder has an `__init__.py` (mypy checks
  `tests` as a package and duplicate module names would clash).
- Prefer plain pytest functions and fixtures (`tests/conftest.py`,
  `tests/unit/<subpackage>/conftest.py`); existing `unittest.TestCase` tests are allowed.
- mypy checks tests too: annotate every test and fixture
  (`def test_merge_keeps_last_value(tmp_path: Path) -> None:`), parametrise generics.
- Docstring rules (`D`) are disabled for tests, but give each test a descriptive name:
  `test_<unit>_<behaviour>_<condition>`.
- Unit tests must not use the network. Inject a fake HTTP session (simple class or
  `unittest.mock` `create_autospec`) into the client. Store small, anonymised,
  real-format responses in `tests/unit/resources/` and load them with
  `importlib.resources` or a `Path` fixture.
- Live network checks belong only under `tests/integration/`; keep requests serial and
  throttled, use public endpoints without credentials, and run them explicitly with
  `make integration`. They are intentionally excluded from `make tests` and `make checks`.
- Credentials: set fake values with `monkeypatch.setenv("INVESTING_EMAIL", "user@example.com")`
  and mark fake secrets with `# pragma: allowlist secret` for detect-secrets.
- Filesystem: write only into `tmp_path`; never read or write the real `data/` folder.
- Numeric assertions: `pytest.approx`, `np.testing.assert_allclose`,
  `pd.testing.assert_series_equal` / `assert_frame_equal` with explicit tolerances.
- Test edge cases and error branches (`pytest.raises(..., match=...)`): coverage is measured with `branch = true` and must stay ≥ 95 %.
- Use `pytest.mark.parametrize` instead of loops inside a test.
- Run a single unit file quickly with `.venv/bin/python -m pytest tests/unit/<path> -q --no-cov`, then the full `make tests` before finishing.
