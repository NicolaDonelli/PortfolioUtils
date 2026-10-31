---
name: 'Time-series analysis'
description: 'Rules for the analysis subpackage: price panels, returns, risk metrics, portfolio optimization and back-tests without look-ahead bias.'
applyTo: 'portfolio_utils/analysis/**/*.py,tests/analysis/**/*.py'
---
# `portfolio_utils.analysis`

- Inputs are pandas objects with a sorted, unique, tz-naive `DatetimeIndex`; columns are
  instrument slugs (the CSV file stems). Validate this at the public boundary.
- Only `loading.py` performs I/O (reading CSVs from a configurable data directory).
  Everything else is a pure, vectorised function: no loops over rows, no `inplace=True`,
  no chained assignment.
- Never import from `portfolio_utils.download`.
- **Calendar alignment**: ETFs trade on different exchanges/holidays. Align with an explicit
  policy (`inner` join or forward-fill with a `limit`); never back-fill (look-ahead).
- **Returns**: simple returns to aggregate across assets (portfolio returns), log returns to
  aggregate over time. Make the choice explicit in parameter names.
- **Annualization**: infer periods per year from the index frequency (252 daily, 52 weekly,
  12 monthly) or take it as a parameter; never hard-code silently.
- **Risk-free rate** is always an explicit parameter (annual, decimal).
- **Dividends**: investing.com prices are usually not dividend-adjusted. Flag distributing
  ETFs in results; prefer accumulating share classes for performance comparison.
- **Currencies**: do not mix instruments in different currencies without conversion; the
  currency comes from the `.meta.json` sidecar.
- **No look-ahead**: weights used from date t+1 are computed only with data up to date t;
  back-tests must make the rebalancing lag explicit.
- Covariance estimates: offer shrinkage (Ledoit-Wolf) and check positive semi-definiteness
  before optimization.
- Randomness (bootstrap, Monte Carlo) only through an injected `numpy.random.Generator`
  or a `seed` parameter.
- See the `timeseries-analysis` and `portfolio-construction` skills for formulas and methods.
