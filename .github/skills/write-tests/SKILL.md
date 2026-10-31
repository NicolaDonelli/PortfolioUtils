---
name: write-tests
description: Write pytest tests for PortfolioUtils that pass strict mypy, never use the network, use recorded fixtures for investing.com responses and keep branch coverage at or above 95%. Use when adding features, fixing bugs (write the failing test first) or when coverage is too low.
argument-hint: "[module or function to test]"
---
# Write tests

## Procedure (TDD)

1. Locate the unit under test and its target test file: `portfolio_utils/a/b.py` →
   `tests/a/test_b.py`. Create missing `tests/a/__init__.py`.
2. Write the failing test first, starting from [the template](./test_template.py).
3. Run it alone: `.venv/bin/python -m pytest tests/a/test_b.py -q --no-cov`.
4. Implement the minimum code to pass, then refactor.
5. Run `make mypy tests` and check the coverage report (`Missing` column).

## Rules

- Annotate every test and fixture; mypy checks the `tests` package with strict flags.
- No network: build the client with a fake session that returns recorded payloads from
  `tests/resources/`. Never call investing.com from tests.
- Recorded payloads: small, anonymised (no cookies, tokens, e-mail, account ids),
  named after the scenario (`historical_daily_ok.json`, `login_invalid.json`).
- Fake credentials via `monkeypatch.setenv`, marked `# pragma: allowlist secret`.
- Files only in `tmp_path`. Never touch the real `data/` folder.
- Numeric checks with explicit tolerances (`pytest.approx(rel=1e-9)`,
  `np.testing.assert_allclose`, `pd.testing.assert_frame_equal(check_freq=False)`).
- Cover the error branches with `pytest.raises(ExcType, match="...")`.
- Prefer `pytest.mark.parametrize` over loops; one behaviour per test.

## What to test per area

- **settings**: missing env vars → clear error; values masked in `repr`.
- **download/client**: retry on 429/5xx with backoff (inject a fake sleep), no retry on 4xx,
  timeout propagated, login failure → `AuthenticationError`.
- **download/historical**: parsing of recorded payloads, unexpected format →
  `UnexpectedResponseError`, date range splitting.
- **download/storage**: schema, atomic write, incremental merge (duplicates, ordering),
  folder creation.
- **analysis**: known small examples computed by hand, edge cases (constant prices, NaN,
  single observation, misaligned calendars), invariants (weights sum to 1, no negative
  weights when long-only).
