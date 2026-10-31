---
name: add-dependency
description: Add, upgrade or remove a Python dependency in PortfolioUtils the way the project expects (pyproject.toml + uv pip compile through make, MIT-compatible licence, typing stubs for strict mypy). Use when code needs a new library such as pandas, numpy, scipy or curl_cffi, or when mypy reports missing stubs.
argument-hint: "<package> [runtime|dev]"
---
# Add a dependency

This project has **no** `uv.lock` and does not use `uv add` or `pip install` directly.
Dependencies are declared in `pyproject.toml` and the Makefile compiles and syncs them.

## Procedure

1. **Decide the group**
   - Runtime (imported by `portfolio_utils`): `[project].dependencies`.
   - Tooling, tests, typing stubs: `[dependency-groups].dev`.
2. **Check the licence** (the package is MIT and `licensecheck` runs with `zero = true`):
   MIT, BSD, Apache-2.0, ISC, PSF and similar permissive licences are fine. GPL/AGPL are not.
   LGPL/MPL need the owner's approval. Check on PyPI before adding.
3. **Edit `pyproject.toml`** with a lower bound only: `"pandas>=2.2"`. Keep lists sorted.
4. **Typing**: if the library ships no type hints, add its stubs to the dev group
   (e.g. `pandas-stubs`, `scipy-stubs`, `types-requests`). Never silence mypy instead.
5. **Compile and sync**:
   ```bash
   make setup_dev   # recompiles requirements/requirements_dev.txt and syncs .venv
   make reqs        # recompiles requirements/requirements.txt (runtime, used by licensecheck)
   ```
   `requirements/*.txt` are generated and git-ignored: never edit or commit them.
6. **Verify**: `make licensecheck mypy tests`.
7. **Commit** separately: `chore(deps): add pandas for time series handling.`

## Suggested libraries for this project (all MIT/BSD/Apache)

| Need | Library | Group |
|---|---|---|
| DataFrames / time series | `pandas`, `numpy` | runtime |
| Typing for pandas / scipy | `pandas-stubs`, `scipy-stubs` | dev |
| HTTP behind Cloudflare | `curl_cffi` | runtime |
| Settings from env / `.env` | `pydantic-settings` (or `python-dotenv`) | runtime |
| Optimization | `scipy` (optionally `PyPortfolioOpt`) | runtime |
| Property-based tests | `hypothesis` (MPL-2.0, dev only: ask first) | dev |
