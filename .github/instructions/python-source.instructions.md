---
name: 'Python source code'
description: 'Conventions for library code in portfolio_utils: strict typing, Sphinx docstrings checked by pydoclint, logging, errors, small functions.'
applyTo: 'portfolio_utils/**/*.py'
---
# Library code in `portfolio_utils/`

## Module skeleton

Every module starts with a one-line module docstring, then imports (ruff/isort order:
stdlib, third party, first party `portfolio_utils`), then a module logger.

```python
"""Risk and performance metrics for price and return series."""

from __future__ import annotations

import logging
from typing import Final

import numpy as np
import pandas as pd

from portfolio_utils.exceptions import InsufficientDataError

logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR: Final = 252
```

## Docstrings (pydoclint, Sphinx style)

- Use `:param <name>:` for every argument, `:return:` when the function returns a value,
  `:raises <ExceptionType>:` for every exception raised explicitly in the body.
- Do not repeat types in the docstring: the signature is the single source of truth.
- Class docstring documents the class; `__init__` parameters may be documented either in
  the class docstring or in `__init__` (`allow-init-docstring = true`), not in both.
- Examples must be runnable doctests.

```python
def annualized_volatility(
    returns: pd.Series[float], periods_per_year: int = TRADING_DAYS_PER_YEAR
) -> float:
    """Compute the annualized volatility of a periodic return series.

    :param returns: Periodic simple returns indexed by date.
    :param periods_per_year: Number of return periods in one year.
    :return: Annualized standard deviation of ``returns``.
    :raises InsufficientDataError: If fewer than two observations are available.

    >>> r = pd.Series([0.01, -0.02, 0.015])
    >>> round(annualized_volatility(r), 4)
    0.3005
    """
    if returns.count() < 2:
        raise InsufficientDataError("At least two returns are required.")
    return float(returns.std(ddof=1) * np.sqrt(periods_per_year))
```

## Typing

- No implicit `Any`: wrap numpy / pandas scalars with `float(...)`, `int(...)` or use
  `typing.cast` after validating the value, otherwise mypy reports `warn_return_any`.
- Parametrise generics everywhere: `dict[str, float]`, `pd.Series[float]`,
  `npt.NDArray[np.float64]` (`import numpy.typing as npt`).
- Accept abstract collections (`Sequence[str]`, `Mapping[str, float]`), return concrete ones.
- Third-party packages without type information need stubs declared in the dev group
  (`pandas-stubs`, `scipy-stubs`, `types-...`), not `# type: ignore`.

## Design rules

- Pure functions for computations; I/O isolated in dedicated modules
  (`download/client.py`, `download/storage.py`, `analysis/loading.py`).
- Dependency injection for anything external (HTTP session, clock, data directory) so tests
  can pass fakes.
- Public API of each subpackage is listed explicitly in its `__init__.py` `__all__`.
- Validate inputs at the boundary and raise specific exceptions from `exceptions.py`.
- No mutable default arguments, no global mutable state, no `print`.
- Keep functions under ~40 lines and McCabe complexity ≤ 7: extract helpers instead of
  nesting conditionals.
