"""Walk-forward portfolio simulation with lagged estimates and linear costs."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import cast

import numpy as np
import pandas as pd

from portfolio_utils.analysis._validation import validate_datetime_index
from portfolio_utils.analysis.optimization import OptimizationResult

_MIN_WINDOW = 2
_TURNOVER_TOLERANCE = 1e-8
_BASIS_POINTS = 10_000.0
PortfolioOptimizer = Callable[["pd.DataFrame"], "OptimizationResult | pd.Series[float]"]


@dataclass(frozen=True)
class BacktestResult:
    """Net strategy returns, daily weights, turnover, and assumptions.

    :ivar returns: Portfolio simple returns after the modeled trading costs.
    :ivar weights: Asset weights applied at the start of each reported period.
    :ivar turnover: One-way traded notional as a fraction of portfolio value.
    :ivar assumptions: Backtest configuration used for the simulation.
    :ivar limitations: Known simulation and input-data caveats.
    """

    returns: pd.Series[float]
    weights: pd.DataFrame
    turnover: pd.Series[float]
    assumptions: Mapping[str, str | int | float]
    limitations: tuple[str, ...]


def walk_forward_backtest(
    returns: pd.DataFrame,
    optimizer: PortfolioOptimizer,
    *,
    estimation_window: int,
    rebalancing_frequency: str,
    transaction_cost_bps: float,
) -> BacktestResult:
    """Backtest a strategy with estimates lagged by one return observation.

    At each rebalance date, the optimizer receives the immediately preceding
    ``estimation_window`` rows. Weights first apply to that date's return.
    Trading costs are basis points multiplied by absolute one-way turnover.

    :param returns: Complete, aligned simple-return panel with dated rows.
    :param optimizer: Callable accepting historical data and returning an
        optimization result or weight series.
    :param estimation_window: Number of preceding returns used at each rebalance.
    :param rebalancing_frequency: Pandas period such as ``"M"`` or ``"Q"``.
    :param transaction_cost_bps: Linear cost per unit of turnover, in basis points.
    :raises RuntimeError: If the optimizer fails or returns invalid weights.
    :return: Net portfolio returns, applied weights, turnover, and caveats.
    """
    periods = _validate_inputs(
        returns, estimation_window, rebalancing_frequency, transaction_cost_bps
    )
    portfolio_returns: list[float] = []
    portfolio_dates: list[pd.Timestamp] = []
    applied_weights: list[pd.Series[float]] = []
    turnover_values: list[float] = []
    held_weights: pd.Series[float] | None = None
    for row_number in range(estimation_window, len(returns)):
        should_rebalance = (
            held_weights is None or periods[row_number] != periods[row_number - 1]
        )
        turnover = 0.0
        if should_rebalance:
            history = returns.iloc[row_number - estimation_window : row_number]
            held_weights, turnover = _rebalance(
                optimizer, history, returns.columns, held_weights
            )
        if held_weights is None:
            raise RuntimeError("The optimizer did not produce portfolio weights.")
        current_returns = returns.iloc[row_number]
        gross_return = float((held_weights * current_returns).sum())
        cost = turnover * transaction_cost_bps / _BASIS_POINTS
        if 1.0 + gross_return <= 0.0:
            raise RuntimeError(
                "Portfolio value became non-positive during backtesting."
            )
        portfolio_dates.append(returns.index[row_number])
        portfolio_returns.append(gross_return - cost)
        applied_weights.append(held_weights.copy())
        turnover_values.append(turnover)
        held_weights = held_weights * (1.0 + current_returns) / (1.0 + gross_return)

    date_index = pd.DatetimeIndex(portfolio_dates)
    net_returns = pd.Series(
        portfolio_returns, index=date_index, name="portfolio_return"
    )
    weights = pd.DataFrame(applied_weights, index=date_index)
    weights.columns.name = "instrument"
    turnover_series = pd.Series(turnover_values, index=date_index, name="turnover")
    assumptions: dict[str, str | int | float] = {
        "estimation_window": estimation_window,
        "rebalancing_frequency": rebalancing_frequency,
        "transaction_cost_bps": transaction_cost_bps,
        "weight_timing": "trained through t-1; applied from t",
    }
    limitations = (
        "Linear transaction costs omit market impact, taxes, and bid-ask spread variation.",
        "Short ETF histories and omitted/delisted instruments can create "
        "survivorship and selection bias.",
        "Currency conversion and dividend reinvestment are not modeled.",
        "Past performance does not predict future returns.",
    )
    return BacktestResult(
        net_returns, weights, turnover_series, assumptions, limitations
    )


def _validate_inputs(
    returns: pd.DataFrame,
    estimation_window: int,
    rebalancing_frequency: str,
    transaction_cost_bps: float,
) -> pd.PeriodIndex:
    """Validate backtest data and assumptions, returning calendar periods.

    :param returns: Dated simple-return panel.
    :param estimation_window: Number of preceding observations in each estimate.
    :param rebalancing_frequency: Pandas period frequency.
    :param transaction_cost_bps: Linear trading cost in basis points.
    :return: Period label for each return observation.
    """
    _validate_config(estimation_window, rebalancing_frequency, transaction_cost_bps)
    _validate_return_data(returns, estimation_window)
    return _calendar_periods(
        cast(pd.DatetimeIndex, returns.index), rebalancing_frequency
    )


def _validate_config(
    estimation_window: int,
    rebalancing_frequency: str,
    transaction_cost_bps: float,
) -> None:
    """Validate backtest period and transaction cost assumptions.

    :param estimation_window: Number of preceding return rows.
    :param rebalancing_frequency: Pandas period frequency string.
    :param transaction_cost_bps: Linear cost per turnover.
    :raises ValueError: If any assumption is invalid.
    """
    if estimation_window < _MIN_WINDOW:
        raise ValueError("estimation_window must be at least 2.")
    if not rebalancing_frequency:
        raise ValueError("rebalancing_frequency must be non-empty.")
    if not math.isfinite(transaction_cost_bps) or transaction_cost_bps < 0:
        raise ValueError("transaction_cost_bps must be finite and non-negative.")


def _validate_return_data(returns: pd.DataFrame, estimation_window: int) -> None:
    """Validate complete simple returns and the available backtest period.

    :param returns: Dated simple-return panel.
    :param estimation_window: Number of observations reserved for estimation.
    :raises ValueError: If the panel is invalid or too short.
    """
    validate_datetime_index(returns.index)
    if returns.empty or not returns.columns.is_unique or len(returns.columns) == 0:
        raise ValueError("returns must contain unique assets and dated observations.")
    values = returns.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= -1.0).any():
        raise ValueError("returns must be finite simple returns greater than -1.")
    if len(returns) <= estimation_window:
        raise ValueError("At least one return must follow the estimation window.")


def _calendar_periods(
    index: pd.DatetimeIndex, rebalancing_frequency: str
) -> pd.PeriodIndex:
    """Convert dates to rebalance periods.

    :param index: Validated return dates.
    :param rebalancing_frequency: Pandas period frequency string.
    :raises ValueError: If the frequency is invalid.
    :return: Period label for each date.
    """
    try:
        return index.to_period(rebalancing_frequency)
    except ValueError as error:
        raise ValueError(
            "rebalancing_frequency must be a valid pandas period string."
        ) from error


def _rebalance(
    optimizer: PortfolioOptimizer,
    history: pd.DataFrame,
    assets: pd.Index[str],
    current_weights: pd.Series[float] | None,
) -> tuple[pd.Series[float], float]:
    """Estimate target weights and compute actual one-way turnover.

    :param optimizer: Weight estimator run only on ``history``.
    :param history: Estimation data ending before the application date.
    :param assets: Full portfolio asset order.
    :param current_weights: Drifted pre-trade weights, or ``None`` at inception.
    :raises RuntimeError: If the optimizer fails or returns invalid weights.
    :return: Target weights and absolute one-way traded notional.
    """
    try:
        result = optimizer(history.copy())
    except Exception as error:
        raise RuntimeError(
            "The portfolio optimizer failed during backtesting."
        ) from error
    proposed = result.weights if isinstance(result, OptimizationResult) else result
    if set(proposed.index) != set(assets):
        raise RuntimeError("Optimizer weights must match the return panel assets.")
    proposed = proposed.reindex(assets).astype(float)
    if not np.isfinite(proposed.to_numpy(dtype=float)).all():
        raise RuntimeError("Optimizer returned non-finite weights.")
    if abs(float(proposed.sum()) - 1.0) > _TURNOVER_TOLERANCE:
        raise RuntimeError("Optimizer weights must sum to one.")
    turnover = (
        float(proposed.abs().sum())
        if current_weights is None
        else float((proposed - current_weights).abs().sum())
    )
    return proposed, turnover
