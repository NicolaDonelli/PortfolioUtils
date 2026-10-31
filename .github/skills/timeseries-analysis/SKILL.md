---
name: timeseries-analysis
description: Implement or use PortfolioUtils time-series analysis of ETF prices loaded from data/ CSV files (alignment of calendars, simple and log returns, resampling, CAGR, volatility, Sharpe, Sortino, Calmar, maximum drawdown, beta, correlation, rolling metrics). Use when computing or adding performance and risk statistics or when analysing downloaded ETFs.
argument-hint: "[metric or analysis, e.g. 'rolling 1y Sharpe for all ETFs']"
---
# Time-series analysis

## Procedure

1. **Load** with `analysis/loading.py`: read `data/*.csv` (+ `.meta.json`) into a wide
   price panel `DataFrame[date × slug]` of `close` prices. Validate index (sorted, unique,
   `DatetimeIndex`) and report instruments with different currencies or distributing share
   classes.
2. **Align** calendars with an explicit policy: `how="inner"` for comparisons, or
   forward-fill with `limit` (e.g. 5 business days) for portfolio simulations. Never bfill.
3. **Returns**: `prices.pct_change()` (simple) or `np.log(prices).diff()` (log); drop the
   first NaN row explicitly. Resample prices (not returns) with `.resample("ME").last()`.
4. **Metrics**: implement as pure functions in `metrics.py` following
   [the formulas reference](./reference/formulas.md); every function takes
   `periods_per_year` and, when relevant, `risk_free_rate` explicitly.
5. **Test** each metric on a tiny hand-computed example plus edge cases (constant prices,
   NaN, a single observation), then run the `quality-gate` skill.

## When analysing the owner's data (not writing library code)

- Use the library functions from a temporary script or the terminal; do not write results
  into `data/` and do not commit outputs.
- Report results as a table: instrument, period covered, CAGR, volatility, Sharpe, max
  drawdown, with the assumptions (risk-free rate, alignment policy, currency).
- State clearly that past performance does not predict future returns.
