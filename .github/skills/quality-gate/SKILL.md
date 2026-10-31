---
name: quality-gate
description: Run and fix the PortfolioUtils quality pipeline through the Makefile (ruff format, ruff lint, pydoclint, strict mypy, licensecheck, pytest with 95% branch coverage, Sphinx docs). Use before finishing any code change, when a check fails, or when asked to run the checks, make checks, or fix lint, typing, docstring or test failures.
argument-hint: "[all | format | lint | mypy | tests | licensecheck | docs]"
---
# Quality gate

The real gate of this repository is `make checks`, run by the git pre-push hook and by CI.
Reproduce it locally, one target at a time, so failures are easy to read.

## Procedure

1. Auto-fix first (these modify files):
   ```bash
   make format && make lint
   ```
2. Run the read-only checks with the helper script, which runs each target separately
   and prints a summary (`all` is the default):
   ```bash
   bash .github/skills/quality-gate/scripts/run_checks.sh            # all checks
   bash .github/skills/quality-gate/scripts/run_checks.sh mypy tests # a subset
   ```
   Targets: `check_format`, `check_lint` (ruff + pydoclint on `portfolio_utils`), `mypy`
   (packages `portfolio_utils` and `tests`), `tests` (pytest + doctests + coverage),
   `licensecheck` (needs network), `docs` (Sphinx, also run by CI).
3. Fix the root cause of each failure (table below), then re-run only the failing target.
4. Finish with `make checks`. Report which targets passed and anything you could not run.

## Fixing common failures

| Failure | Typical fix |
|---|---|
| `ruff format --check` | Run `make format`. Never hand-format against ruff. |
| ruff `F401` unused import | Remove it; in `__init__.py` re-exports list them in `__all__`. |
| pydoclint `DOC101`/`DOC103` (args mismatch) | Make `:param:` fields match the signature exactly, same order. |
| pydoclint `DOC201` (missing return) | Add `:return:` describing the value (no type). |
| pydoclint `DOC501`/`DOC503` (raises) | Add `:raises ExcType:` for every exception raised in the body. |
| pydoclint style mismatch | Use Sphinx fields only (`:param x:`), not Google/Numpy sections. |
| mypy `Missing type parameters for generic type` | `list` → `list[str]`, `pd.Series` → `pd.Series[float]`. |
| mypy `Returning Any from function declared to return "float"` | Wrap with `float(...)` or validate and `cast`. |
| mypy `Call to untyped function` / `missing library stubs` | Add stubs to the dev group with the `add-dependency` skill (`pandas-stubs`, `scipy-stubs`, `types-...`). |
| mypy errors in tests | Annotate tests and fixtures (`-> None`, typed parameters). |
| coverage `< 95` | Read the `Missing` column (`show_missing = true`) and add tests for those lines and branches. |
| doctest failure | Fix the example output or the code; doctests are collected by `--doctest-modules`. |
| licensecheck incompatible | Replace the dependency with an MIT-compatible one; do not add it to `ignore_packages`. |

## Never

- Lower `fail_under`, remove mypy flags, add ruff ignores or `ignore_packages` entries.
- Add blanket `# noqa` / `# type: ignore` / `# pragma: no cover`.
- Use `git push --no-verify` to skip the pre-push `make checks`.
