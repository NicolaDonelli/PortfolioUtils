# Formulas (decimal units, `P` = periods per year)

| Metric | Definition |
|---|---|
| Simple return | r_t = p_t / p_{t-1} − 1 |
| Log return | l_t = ln(p_t / p_{t-1}) |
| Cumulative return | Π(1 + r_t) − 1 |
| CAGR | (p_end / p_start)^(365.25 / days) − 1 (calendar days between first and last date) |
| Annualized mean | mean(r) · P (arithmetic) |
| Annualized volatility | std(r, ddof=1) · √P |
| Sharpe ratio | (mean(r − rf_p) · P) / (std(r − rf_p) · √P), with rf_p = (1 + rf)^(1/P) − 1 |
| Downside deviation | √(mean(min(r − mar_p, 0)²)) · √P |
| Sortino ratio | (mean(r − mar_p) · P) / downside deviation |
| Drawdown | DD_t = p_t / max_{s≤t} p_s − 1 |
| Maximum drawdown | min_t DD_t (negative number) |
| Calmar ratio | CAGR / |max drawdown| |
| Beta vs benchmark | cov(r, r_b) / var(r_b) |
| Tracking error | std(r − r_b) · √P |
| Information ratio | mean(r − r_b) · P / tracking error |
| Historical VaR (α) | −quantile(r, 1 − α) |
| Historical CVaR (α) | −mean(r | r ≤ quantile(r, 1 − α)) |

Periods per year: daily 252, weekly 52, monthly 12, quarterly 4.
Rolling versions: apply the same function on `.rolling(window)` with `min_periods = window`.
