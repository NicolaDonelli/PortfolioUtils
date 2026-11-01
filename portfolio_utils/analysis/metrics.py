"""Pure, vectorized portfolio performance and risk statistics."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

import numpy as np
import pandas as pd

from portfolio_utils.analysis._validation import (
    validate_datetime_index,
    validate_price_panel,
    validate_return_series,
)
from portfolio_utils.analysis.returns import align_prices, prices_to_returns

_MIN_PRICE_COUNT = 2
_MIN_RETURN_COUNT = 2


@dataclass(frozen=True)
class PerformanceAssumptions:
    """Explicit conventions attached to a performance summary.

    :ivar periods_per_year: Number of return observations per year.
    :ivar risk_free_rate: Annual risk-free return in decimal units.
    :ivar alignment_policy: ``"inner"`` or bounded ``"ffill"``.
    :ivar currency: Reporting currency, or ``None`` if not established.
    :ivar dividend_adjusted: Whether dividends are included in price data.
    :ivar ffill_limit: Maximum forward-fill distance when using ``"ffill"``.
    """

    periods_per_year: int
    risk_free_rate: float
    alignment_policy: str
    currency: str | None
    dividend_adjusted: bool | None
    ffill_limit: int | None = None


def _validate_periods(periods_per_year: int) -> None:
    """Validate an explicit annualization frequency.

    :param periods_per_year: Number of observations per year.
    :raises ValueError: If the frequency is not a positive integer.
    """
    if (
        isinstance(periods_per_year, bool)
        or not isinstance(periods_per_year, int)
        or periods_per_year < 1
    ):
        raise ValueError("periods_per_year must be a positive integer.")


def _validate_rate(rate: float, name: str) -> None:
    """Validate an annual decimal rate.

    :param rate: Annualized rate as a decimal.
    :param name: Rate label for the error message.
    :raises ValueError: If the rate is non-finite or at most -100%.
    """
    if not math.isfinite(rate) or rate <= -1.0:
        raise ValueError(f"{name} must be finite and greater than -1.")


def _validate_prices(prices: pd.Series[float]) -> None:
    """Validate a dated positive price series.

    :param prices: Price history indexed by dates.
    :raises ValueError: If fewer than two valid prices or invalid dates/prices
        are present.
    """
    if len(prices) < _MIN_PRICE_COUNT:
        raise ValueError("At least two prices are required.")
    validate_datetime_index(prices.index)
    if not np.isfinite(prices.to_numpy(dtype=float)).all():
        raise ValueError("Prices must contain only finite values.")
    if (prices <= 0.0).any():
        raise ValueError("Prices must be positive.")


def cumulative_return(returns: pd.Series[float]) -> float:
    """Calculate the compounded cumulative simple return.

    :param returns: One-dimensional simple return series.
    :raises ValueError: If returns are invalid or fewer than one observation.
    :return: Cumulative return as a decimal.

    >>> import pandas as pd
    >>> cumulative_return(
    ...     pd.Series(
    ...         [0.1, -0.1]
    ...     )
    ... )
    -0.009999999999999898
    """
    try:
        validate_return_series(returns)
    except ValueError:
        raise
    return float(np.prod(1.0 + returns.to_numpy(dtype=float)) - 1.0)


def cagr(prices: pd.Series[float]) -> float:
    """Calculate CAGR using elapsed calendar days between first and last prices.

    :param prices: Positive price history indexed by dates.
    :raises ValueError: If prices are invalid or span no positive time.
    :return: Compound annual growth rate as a decimal.

    >>> import pandas as pd
    >>> dates = pd.to_datetime(
    ...     [
    ...         "2023-01-01",
    ...         "2024-01-01",
    ...     ]
    ... )
    >>> round(
    ...     cagr(
    ...         pd.Series(
    ...             [
    ...                 100.0,
    ...                 110.0,
    ...             ],
    ...             index=dates,
    ...         )
    ...     ),
    ...     4,
    ... )
    0.1001
    """
    _validate_prices(prices)
    elapsed_days = (prices.index[-1] - prices.index[0]).days
    if elapsed_days <= 0:
        raise ValueError("CAGR requires a positive calendar-day span.")
    return float((prices.iloc[-1] / prices.iloc[0]) ** (365.25 / elapsed_days) - 1.0)


def annualized_return(returns: pd.Series[float], *, periods_per_year: int) -> float:
    """Calculate the arithmetic annualized mean simple return.

    :param returns: One-dimensional simple return series.
    :param periods_per_year: Number of return observations per year.
    :raises ValueError: If returns or annualization frequency are invalid.
    :return: Arithmetic annualized return as a decimal.
    """
    _validate_periods(periods_per_year)
    try:
        validate_return_series(returns)
    except ValueError:
        raise
    return float(returns.mean() * periods_per_year)


def realized_volatility(returns: pd.Series[float]) -> float:
    """Calculate sample standard deviation per return observation.

    :param returns: One-dimensional simple return series.
    :raises ValueError: If fewer than two valid returns are provided.
    :return: Realized volatility per observation.
    """
    try:
        validate_return_series(returns, minimum_observations=_MIN_RETURN_COUNT)
    except ValueError:
        raise
    return float(returns.std(ddof=1))


def annualized_realized_volatility(
    returns: pd.Series[float], *, periods_per_year: int
) -> float:
    """Annualize realized volatility by square-root time.

    :param returns: One-dimensional simple return series.
    :param periods_per_year: Number of return observations per year.
    :raises ValueError: If inputs or annualization frequency are invalid.
    :return: Annualized realized volatility.
    """
    try:
        _validate_periods(periods_per_year)
        return float(realized_volatility(returns) * math.sqrt(periods_per_year))
    except ValueError:
        raise


def annualized_volatility(returns: pd.Series[float], *, periods_per_year: int) -> float:
    """Alias for :func:`annualized_realized_volatility`.

    :param returns: One-dimensional simple return series.
    :param periods_per_year: Number of return observations per year.
    :raises ValueError: If fewer than two valid returns or invalid frequency.
    :return: Annualized realized volatility.
    """
    try:
        return annualized_realized_volatility(
            returns, periods_per_year=periods_per_year
        )
    except ValueError:
        raise


def sharpe_ratio(
    returns: pd.Series[float],
    *,
    periods_per_year: int,
    risk_free_rate: float,
) -> float:
    """Calculate the per-observation Sharpe ratio.

    :param returns: One-dimensional simple return series.
    :param periods_per_year: Number of return observations per year.
    :param risk_free_rate: Annual risk-free return as a decimal.
    :raises ValueError: If inputs are invalid or excess returns have zero
        volatility.
    :return: Per-observation Sharpe ratio.

    >>> import pandas as pd
    >>> sharpe_ratio(
    ...     pd.Series(
    ...         [0.1, -0.1]
    ...     ),
    ...     periods_per_year=2,
    ...     risk_free_rate=0.0,
    ... )
    0.0
    """
    _validate_periods(periods_per_year)
    _validate_rate(risk_free_rate, "risk_free_rate")
    validate_return_series(returns, minimum_observations=_MIN_RETURN_COUNT)
    period_rf = (1.0 + risk_free_rate) ** (1.0 / periods_per_year) - 1.0
    excess = returns - period_rf
    volatility = float(excess.std(ddof=1))
    if not math.isfinite(volatility) or volatility == 0.0:
        raise ValueError("Sharpe ratio is undefined with zero volatility.")
    return float(excess.mean() / volatility)


def annualized_sharpe_ratio(
    returns: pd.Series[float],
    *,
    periods_per_year: int,
    risk_free_rate: float,
) -> float:
    """Calculate the annualized Sharpe ratio.

    :param returns: One-dimensional simple return series.
    :param periods_per_year: Number of return observations per year.
    :param risk_free_rate: Annual risk-free return as a decimal.
    :raises ValueError: If inputs are invalid or excess returns have zero
        volatility.
    :return: Annualized Sharpe ratio.
    """
    try:
        return float(
            sharpe_ratio(
                returns,
                periods_per_year=periods_per_year,
                risk_free_rate=risk_free_rate,
            )
            * math.sqrt(periods_per_year)
        )
    except ValueError:
        raise


def sortino_ratio(
    returns: pd.Series[float],
    *,
    periods_per_year: int,
    risk_free_rate: float,
) -> float:
    """Calculate the per-observation Sortino ratio using risk-free rate as MAR.

    Downside deviation is the root mean square of negative excess returns,
    including zero contributions from observations above the MAR.

    :param returns: One-dimensional simple return series.
    :param periods_per_year: Number of return observations per year.
    :param risk_free_rate: Annual minimum acceptable return as a decimal.
    :raises ValueError: If inputs are invalid or there is no downside
        deviation.
    :return: Per-observation Sortino ratio.
    """
    _validate_periods(periods_per_year)
    _validate_rate(risk_free_rate, "risk_free_rate")
    validate_return_series(returns)
    mar_period = (1.0 + risk_free_rate) ** (1.0 / periods_per_year) - 1.0
    excess = returns - mar_period
    downside = np.minimum(excess.to_numpy(dtype=float), 0.0)
    downside_deviation = float(np.sqrt(np.mean(np.square(downside))))
    if downside_deviation == 0.0:
        raise ValueError("Sortino ratio is undefined without downside deviation.")
    return float(excess.mean() / downside_deviation)


def annualized_sortino_ratio(
    returns: pd.Series[float],
    *,
    periods_per_year: int,
    risk_free_rate: float,
) -> float:
    """Calculate the annualized Sortino ratio.

    :param returns: One-dimensional simple return series.
    :param periods_per_year: Number of return observations per year.
    :param risk_free_rate: Annual minimum acceptable return as a decimal.
    :raises ValueError: If inputs are invalid or there is no downside
        deviation.
    :return: Annualized Sortino ratio.
    """
    try:
        return float(
            sortino_ratio(
                returns,
                periods_per_year=periods_per_year,
                risk_free_rate=risk_free_rate,
            )
            * math.sqrt(periods_per_year)
        )
    except ValueError:
        raise


def max_drawdown(prices: pd.Series[float]) -> float:
    """Return the largest peak-to-trough drawdown as a negative decimal.

    :param prices: Positive price history.
    :raises ValueError: If prices are invalid or fewer than two observations.
    :return: Maximum drawdown, for example ``-0.2`` for a 20% loss.

    >>> import pandas as pd
    >>> dates = pd.date_range(
    ...     "2024-01-01",
    ...     periods=3,
    ...     freq="D",
    ... )
    >>> max_drawdown(
    ...     pd.Series(
    ...         [
    ...             100.0,
    ...             110.0,
    ...             99.0,
    ...         ],
    ...         index=dates,
    ...     )
    ... )
    -0.09999999999999998
    """
    try:
        _validate_prices(prices)
    except ValueError:
        raise
    drawdowns = prices / prices.cummax() - 1.0
    return float(drawdowns.min())


def calmar_ratio(prices: pd.Series[float]) -> float:
    """Calculate CAGR divided by the absolute maximum drawdown.

    :param prices: Positive dated price history.
    :raises ValueError: If prices are invalid or there is no drawdown.
    :return: Calmar ratio.
    """
    drawdown = abs(max_drawdown(prices))
    if drawdown == 0.0:
        raise ValueError("Calmar ratio is undefined without a drawdown.")
    return cagr(prices) / drawdown


def beta(
    asset_returns: pd.Series[float],
    benchmark_returns: pd.Series[float],
    *,
    alignment: str,
) -> float:
    """Estimate asset beta from aligned simple returns.

    :param asset_returns: Asset simple returns.
    :param benchmark_returns: Benchmark simple returns.
    :param alignment: ``"exact"`` requires equal indexes; ``"inner"`` uses
        only shared observations.
    :raises ValueError: If alignment is invalid, observations are insufficient,
        or benchmark variance is zero.
    :return: Sample covariance divided by sample benchmark variance.
    """
    if alignment not in {"exact", "inner"}:
        raise ValueError("alignment must be 'exact' or 'inner'.")
    if alignment == "exact" and not asset_returns.index.equals(benchmark_returns.index):
        raise ValueError("Return indexes must match when alignment='exact'.")
    joined = pd.concat(
        [asset_returns.rename("asset"), benchmark_returns.rename("benchmark")],
        axis=1,
        join="inner",
    ).dropna()
    validate_return_series(
        joined["asset"],
        name="asset_returns",
        minimum_observations=_MIN_RETURN_COUNT,
    )
    validate_return_series(
        joined["benchmark"],
        name="benchmark_returns",
        minimum_observations=_MIN_RETURN_COUNT,
    )
    benchmark_variance = float(joined["benchmark"].var(ddof=1))
    if benchmark_variance == 0.0:
        raise ValueError("Beta is undefined when benchmark variance is zero.")
    return float(joined["asset"].cov(joined["benchmark"]) / benchmark_variance)


def tracking_error(
    asset_returns: pd.Series[float],
    benchmark_returns: pd.Series[float],
    *,
    periods_per_year: int,
) -> float:
    """Calculate annualized sample volatility of active returns.

    :param asset_returns: Asset simple returns.
    :param benchmark_returns: Benchmark simple returns on the same dates.
    :param periods_per_year: Number of return observations per year.
    :raises ValueError: If indexes differ or there are fewer than two returns.
    :return: Annualized tracking error.
    """
    _validate_periods(periods_per_year)
    if not asset_returns.index.equals(benchmark_returns.index):
        raise ValueError("Asset and benchmark indexes must match for tracking error.")
    active = asset_returns - benchmark_returns
    validate_return_series(
        active, name="active_returns", minimum_observations=_MIN_RETURN_COUNT
    )
    return float(active.std(ddof=1) * math.sqrt(periods_per_year))


def information_ratio(
    asset_returns: pd.Series[float],
    benchmark_returns: pd.Series[float],
    *,
    periods_per_year: int,
) -> float:
    """Calculate annualized mean active return divided by tracking error.

    :param asset_returns: Asset simple returns.
    :param benchmark_returns: Benchmark simple returns on the same dates.
    :param periods_per_year: Number of return observations per year.
    :raises ValueError: If active returns are invalid or have zero volatility.
    :return: Annualized information ratio.
    """
    error = tracking_error(
        asset_returns, benchmark_returns, periods_per_year=periods_per_year
    )
    if error == 0.0:
        raise ValueError("Information ratio is undefined with zero tracking error.")
    return float((asset_returns - benchmark_returns).mean() * periods_per_year / error)


def historical_var(returns: pd.Series[float], *, alpha: float) -> float:
    """Calculate historical one-period Value at Risk as a positive loss.

    :param returns: One-dimensional simple return series.
    :param alpha: Confidence level strictly between zero and one.
    :raises ValueError: If returns or confidence level are invalid.
    :return: Historical VaR, defined as ``-quantile(returns, 1-alpha)``.
    """
    try:
        _validate_tail_inputs(returns, alpha)
    except ValueError:
        raise
    return float(-returns.quantile(1.0 - alpha))


def historical_cvar(returns: pd.Series[float], *, alpha: float) -> float:
    """Calculate historical conditional VaR as a positive tail loss.

    :param returns: One-dimensional simple return series.
    :param alpha: Confidence level strictly between zero and one.
    :raises ValueError: If returns or confidence level are invalid.
    :return: Negative mean return at or below the lower-tail quantile.
    """
    try:
        _validate_tail_inputs(returns, alpha)
    except ValueError:
        raise
    quantile = float(returns.quantile(1.0 - alpha))
    tail = returns[returns <= quantile]
    return float(-tail.mean())


def _validate_tail_inputs(returns: pd.Series[float], alpha: float) -> None:
    """Validate return series and confidence level for tail-risk metrics.

    :param returns: One-dimensional simple return series.
    :param alpha: Confidence level.
    :raises ValueError: If returns or confidence level are invalid.
    """
    validate_return_series(returns)
    if not math.isfinite(alpha) or not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be strictly between zero and one.")


def _safe_metric(metric: Callable[[], float]) -> float:
    """Return NaN when a statistic is mathematically undefined.

    :param metric: Zero-argument metric calculation.
    :return: The metric result or NaN for a ``ValueError`` domain failure.
    """
    try:
        return metric()
    except ValueError:
        return math.nan


def performance_summary(
    prices: pd.DataFrame,
    *,
    assumptions: PerformanceAssumptions,
) -> pd.DataFrame:
    """Build a per-instrument metric table with explicit assumptions.

    The returned DataFrame stores assumptions and limitations in ``attrs`` so
    they remain attached when presenting the table. Undefined ratios are NaN.

    :param prices: Wide close-price panel.
    :param assumptions: Explicit annualization, risk-free, calendar, currency,
        and dividend-treatment conventions.
    :return: Table indexed by asset and containing eight performance metrics.
    """
    _validate_periods(assumptions.periods_per_year)
    _validate_rate(assumptions.risk_free_rate, "risk_free_rate")
    validate_price_panel(prices)
    aligned_prices = _aligned_prices(prices, assumptions)
    aligned_returns = prices_to_returns(
        aligned_prices,
        method="simple",
        alignment_policy="inner",
    )
    records: dict[str, dict[str, float]] = {}
    for instrument in aligned_prices.columns:
        return_series = aligned_returns[instrument]
        records[instrument] = {
            "cumulative_return": cumulative_return(return_series),
            "annualized_return": annualized_return(
                return_series, periods_per_year=assumptions.periods_per_year
            ),
            "realized_volatility": _safe_metric(
                partial(realized_volatility, return_series)
            ),
            "annualized_realized_volatility": _safe_metric(
                partial(
                    annualized_realized_volatility,
                    return_series,
                    periods_per_year=assumptions.periods_per_year,
                )
            ),
            "sharpe_ratio": _safe_metric(
                partial(
                    sharpe_ratio,
                    return_series,
                    periods_per_year=assumptions.periods_per_year,
                    risk_free_rate=assumptions.risk_free_rate,
                )
            ),
            "annualized_sharpe_ratio": _safe_metric(
                partial(
                    annualized_sharpe_ratio,
                    return_series,
                    periods_per_year=assumptions.periods_per_year,
                    risk_free_rate=assumptions.risk_free_rate,
                )
            ),
            "sortino_ratio": _safe_metric(
                partial(
                    sortino_ratio,
                    return_series,
                    periods_per_year=assumptions.periods_per_year,
                    risk_free_rate=assumptions.risk_free_rate,
                )
            ),
            "annualized_sortino_ratio": _safe_metric(
                partial(
                    annualized_sortino_ratio,
                    return_series,
                    periods_per_year=assumptions.periods_per_year,
                    risk_free_rate=assumptions.risk_free_rate,
                )
            ),
        }
    summary = pd.DataFrame.from_dict(records, orient="index", dtype=float)
    summary.index.name = "instrument"
    limitations = [
        "CSV close prices may not include reinvested dividends.",
        "Short ETF histories and omitted/delisted instruments can create "
        "survivorship and selection bias.",
        "Past performance does not predict future returns.",
    ]
    if assumptions.currency is None:
        limitations.append(
            "Currency was not supplied; cross-currency comparison is unsafe."
        )
    if assumptions.dividend_adjusted is not True:
        limitations.append("Dividend-adjusted total returns are not confirmed.")
    summary.attrs["assumptions"] = {
        "periods_per_year": assumptions.periods_per_year,
        "risk_free_rate": assumptions.risk_free_rate,
        "alignment_policy": assumptions.alignment_policy,
        "ffill_limit": assumptions.ffill_limit,
        "currency": assumptions.currency,
        "dividend_adjusted": assumptions.dividend_adjusted,
    }
    summary.attrs["period"] = (
        aligned_prices.index[0].date().isoformat(),
        aligned_prices.index[-1].date().isoformat(),
    )
    summary.attrs["limitations"] = tuple(limitations)
    return summary


def _aligned_prices(
    prices: pd.DataFrame, assumptions: PerformanceAssumptions
) -> pd.DataFrame:
    """Apply the alignment convention for a performance table.

    :param prices: Input close-price panel.
    :param assumptions: Alignment and fill assumptions.
    :return: Complete price panel with aligned calendars.
    """
    return align_prices(
        prices,
        policy=assumptions.alignment_policy,
        limit=assumptions.ffill_limit,
    )
