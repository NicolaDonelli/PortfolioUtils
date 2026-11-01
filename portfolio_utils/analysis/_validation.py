"""Shared validation helpers for analysis inputs."""

from __future__ import annotations

import numpy as np
import pandas as pd


def validate_datetime_index(index: pd.Index) -> None:
    """Validate a sorted, unique, timezone-naive datetime index.

    :param index: Index to validate.
    :raises ValueError: If the index is not a suitable time-series index.
    """
    if not isinstance(index, pd.DatetimeIndex):
        raise ValueError("Index must be a DatetimeIndex.")
    if index.tz is not None:
        raise ValueError("DatetimeIndex must be timezone-naive.")
    if not index.is_monotonic_increasing:
        raise ValueError("DatetimeIndex must be sorted in ascending order.")
    if not index.is_unique:
        raise ValueError("DatetimeIndex must contain unique timestamps.")


def validate_price_panel(prices: pd.DataFrame) -> None:
    """Validate prices while allowing NaNs from unequal instrument histories.

    :param prices: Wide price panel with date index and instrument columns.
    :raises ValueError: If the panel has invalid labels or price values.
    """
    validate_datetime_index(prices.index)
    if prices.empty or len(prices.columns) == 0:
        raise ValueError("Price panel must contain at least one observation and asset.")
    if not prices.columns.is_unique or any(
        not isinstance(column, str) or not column for column in prices.columns
    ):
        raise ValueError("Price panel columns must be unique non-empty strings.")
    values = prices.to_numpy(dtype=float)
    present = values[~np.isnan(values)]
    if not np.isfinite(present).all():
        raise ValueError("Prices must contain only finite numbers or missing values.")
    if (present <= 0.0).any():
        raise ValueError("Prices must be positive.")


def validate_return_series(
    returns: pd.Series[float],
    *,
    name: str = "returns",
    minimum_observations: int = 1,
) -> None:
    """Validate a one-dimensional series of simple returns.

    :param returns: Series of simple returns.
    :param name: Name used in validation messages.
    :param minimum_observations: Minimum number of observations required.
    :raises ValueError: If the return series is invalid or too short.
    """
    if len(returns) < minimum_observations:
        raise ValueError(
            f"{name} must contain at least {minimum_observations} observation(s)."
        )
    values = returns.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError(f"{name} must contain only finite values.")
    if (values <= -1.0).any():
        raise ValueError(f"{name} must be greater than -1.")
