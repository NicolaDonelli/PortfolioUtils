---
name: portfolio-construction
description: Build and back-test ETF portfolios in PortfolioUtils from historical returns (equal weight, inverse volatility, minimum variance, maximum Sharpe, risk parity, hierarchical risk parity) with long-only and weight constraints, covariance shrinkage and walk-forward back-tests free of look-ahead bias. Use when asked to compute portfolio weights, compare allocation strategies or simulate rebalancing.
argument-hint: "[strategy and constraints, e.g. 'min variance, max 30% per ETF, monthly rebalancing']"
---
# Portfolio construction

## Procedure

1. Start from aligned simple returns (`timeseries-analysis` skill) for an explicit
   estimation window (e.g. last 3 years of daily data).
2. Estimate inputs: expected returns (historical mean, optionally shrunk) and covariance
   (sample or Ledoit-Wolf). Check the covariance is positive semi-definite.
3. Compute weights with a function from `optimization.py` (see
   [methods](./reference/methods.md)); constraints are explicit parameters:
   `long_only: bool`, `max_weight: float`, `min_weight: float`, weights sum to 1.
4. Validate the output: weights sum to 1 within 1e-8, bounds respected, no NaN; raise
   `OptimizationError` if the solver fails (never return silently wrong weights).
5. Back-test with `backtest.py`: walk-forward, weights estimated on data up to t, applied
   from t+1, rebalancing frequency and transaction costs as parameters. Report the metrics
   of the resulting portfolio returns and the turnover.
6. Test invariants and a tiny case with a known analytical solution (e.g. two uncorrelated
   assets: minimum variance weights ∝ 1/σ²), then run the `quality-gate` skill.

## Cautions to state in results

- Mean-variance optimization is very sensitive to expected-return estimates: prefer
  minimum variance / risk parity or shrinkage unless the owner asks otherwise.
- Results depend on the period, currency and dividend treatment; past performance does not
  predict future returns. This is not investment advice.
