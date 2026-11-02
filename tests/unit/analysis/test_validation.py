"""Tests for shared analysis input validation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from portfolio_utils.analysis._validation import (
    validate_datetime_index,
    validate_price_panel,
    validate_return_series,
)


@pytest.mark.parametrize(
    ("index", "message"),
    [
        (pd.Index([1, 2]), "DatetimeIndex"),
        (pd.date_range("2024-01-01", periods=2, tz="UTC"), "timezone-naive"),
        (
            pd.to_datetime(["2024-01-02", "2024-01-01"]),
            "sorted in ascending",
        ),
        (
            pd.to_datetime(["2024-01-01", "2024-01-01"]),
            "unique timestamps",
        ),
    ],
)
def test_datetime_index_rejects_invalid_indexes(index: pd.Index, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_datetime_index(index)


@pytest.mark.parametrize(
    ("prices", "message"),
    [
        (pd.DataFrame(index=pd.date_range("2024-01-01", periods=1)), "at least one"),
        (
            pd.DataFrame(index=pd.date_range("2024-01-01", periods=1), columns=[""]),
            "non-empty strings",
        ),
        (
            pd.DataFrame(
                [[1.0, 2.0]],
                columns=["a", "a"],
                index=pd.date_range("2024-01-01", periods=1),
            ),
            "unique non-empty",
        ),
        (
            pd.DataFrame({"a": [np.inf]}, index=pd.date_range("2024-01-01", periods=1)),
            "finite numbers",
        ),
        (
            pd.DataFrame({"a": [0.0]}, index=pd.date_range("2024-01-01", periods=1)),
            "positive",
        ),
    ],
)
def test_price_panel_rejects_invalid_inputs(prices: pd.DataFrame, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_price_panel(prices)


def test_price_panel_allows_missing_prices() -> None:
    prices = pd.DataFrame(
        {"a": [100.0, np.nan]},
        index=pd.date_range("2024-01-01", periods=2),
    )

    validate_price_panel(prices)


@pytest.mark.parametrize(
    ("returns", "minimum_observations", "message"),
    [
        (pd.Series([], dtype=float), 1, "at least 1"),
        (pd.Series([np.nan]), 1, "finite values"),
        (pd.Series([np.inf]), 1, "finite values"),
        (pd.Series([-1.0]), 1, "greater than -1"),
    ],
)
def test_return_series_rejects_invalid_values(
    returns: pd.Series[float], minimum_observations: int, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_return_series(returns, minimum_observations=minimum_observations)


def test_return_series_accepts_valid_values_and_custom_name() -> None:
    returns = pd.Series([0.1, -0.2], dtype=float)
    empty_returns: pd.Series[float] = pd.Series(dtype=float)

    validate_return_series(returns, name="asset returns", minimum_observations=2)

    with pytest.raises(ValueError, match="asset returns"):
        validate_return_series(empty_returns, name="asset returns")
