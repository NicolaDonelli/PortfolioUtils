# Allocation methods

| Method | Weights | Implementation notes |
|---|---|---|
| Equal weight | w_i = 1/N | Baseline for every comparison. |
| Inverse volatility | w_i ∝ 1/σ_i | Ignores correlations; robust. |
| Minimum variance | min wᵀΣw s.t. Σw = 1, bounds | `scipy.optimize.minimize(method="SLSQP")`; closed form without bounds: w ∝ Σ⁻¹1. |
| Maximum Sharpe (tangency) | max (wᵀμ − r_f)/√(wᵀΣw) | Minimise the negative Sharpe with SLSQP; sensitive to μ. |
| Risk parity (ERC) | w_i (Σw)_i = wᵀΣw / N | Minimise Σ_i (w_i (Σw)_i − wᵀΣw/N)²; long-only. |
| Hierarchical risk parity | López de Prado (2016) | Cluster on correlation distance √(½(1−ρ)), quasi-diagonalise, recursive bisection. |

Covariance: sample `returns.cov()`, or Ledoit-Wolf shrinkage (implement the closed form or
use `sklearn.covariance.LedoitWolf` only if the owner approves the dependency).

Back-test loop (walk-forward):

```
for each rebalancing date t:
    window = returns.loc[t - lookback : t]          # data up to and including t
    w_t = strategy(window, constraints)
    apply w_t to returns in (t, next_rebalancing_date]  # starts at t+1
    drift weights with realised returns between rebalancings
    cost = transaction_cost * sum(|w_t - w_drifted|)
```
