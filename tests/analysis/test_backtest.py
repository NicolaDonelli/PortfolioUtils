"""Tests for lagged walk-forward simulation and explicit trading costs."""

from __future__ import annotations

import pandas as pd
import pytest

from portfolio_utils.analysis.backtest import walk_forward_backtest
from portfolio_utils.analysis.optimization import OptimizationResult


def test_backtest_uses_only_previous_returns_and_charges_turnover_cost() -> None:
    index = pd.to_datetime(
        ["2024-01-29", "2024-01-30", "2024-01-31", "2024-02-01", "2024-02-02"]
    )
    returns = pd.DataFrame({"a": [0.1] * 5, "b": [0.1] * 5}, index=index)
    estimation_dates: list[pd.Timestamp] = []

    def equal_weight(history: pd.DataFrame) -> pd.Series[float]:
        estimation_dates.append(history.index[-1])
        return pd.Series({"a": 0.5, "b": 0.5}, dtype=float)

    result = walk_forward_backtest(
        returns,
        equal_weight,
        estimation_window=2,
        rebalancing_frequency="M",
        transaction_cost_bps=100.0,
    )

    assert estimation_dates == [index[1], index[2]]
    assert result.returns.index.tolist() == [index[2], index[3], index[4]]
    assert result.returns.iloc[0] == pytest.approx(0.09)
    assert result.turnover.iloc[0] == pytest.approx(1.0)
    assert result.turnover.iloc[1] == pytest.approx(0.0)
    assert result.weights.sum(axis=1).to_numpy() == pytest.approx([1.0] * 3)
    assert result.assumptions["weight_timing"] == "trained through t-1; applied from t"


def test_backtest_rejects_bad_assumptions_and_optimizer_weights() -> None:
    index = pd.date_range("2024-01-01", periods=4, freq="B")
    returns = pd.DataFrame({"a": [0.01] * 4}, index=index)

    def full_weight(_history: pd.DataFrame) -> pd.Series[float]:
        return pd.Series({"a": 1.0}, dtype=float)

    def partial_weight(_history: pd.DataFrame) -> pd.Series[float]:
        return pd.Series({"a": 0.5}, dtype=float)

    with pytest.raises(ValueError, match="estimation_window"):
        walk_forward_backtest(
            returns,
            full_weight,
            estimation_window=1,
            rebalancing_frequency="M",
            transaction_cost_bps=0.0,
        )
    with pytest.raises(RuntimeError, match="sum to one"):
        walk_forward_backtest(
            returns,
            partial_weight,
            estimation_window=2,
            rebalancing_frequency="M",
            transaction_cost_bps=0.0,
        )
    with pytest.raises(ValueError, match="valid pandas period"):
        walk_forward_backtest(
            returns,
            full_weight,
            estimation_window=2,
            rebalancing_frequency="unknown-period",
            transaction_cost_bps=0.0,
        )


@pytest.mark.parametrize(
    ("estimation_window", "frequency", "cost", "message"),
    [
        (0, "M", 0.0, "estimation_window"),
        (2, "", 0.0, "rebalancing_frequency"),
        (2, "M", -1.0, "transaction_cost_bps"),
        (2, "M", float("inf"), "transaction_cost_bps"),
    ],
)
def test_backtest_rejects_invalid_configuration(
    estimation_window: int, frequency: str, cost: float, message: str
) -> None:
    returns = pd.DataFrame(
        {"a": [0.01] * 4}, index=pd.date_range("2024-01-01", periods=4)
    )

    with pytest.raises(ValueError, match=message):
        walk_forward_backtest(
            returns,
            lambda _history: pd.Series({"a": 1.0}),
            estimation_window=estimation_window,
            rebalancing_frequency=frequency,
            transaction_cost_bps=cost,
        )


@pytest.mark.parametrize(
    "returns",
    [
        pd.DataFrame(index=pd.date_range("2024-01-01", periods=3)),
        pd.DataFrame(
            {"a": [0.01, 0.02, 0.03]},
            index=pd.to_datetime(["2024-01-01", "2024-01-01", "2024-01-02"]),
        ),
        pd.DataFrame(
            {"a": [0.01, float("nan"), 0.03]},
            index=pd.date_range("2024-01-01", periods=3),
        ),
        pd.DataFrame(
            {"a": [-1.0, 0.02, 0.03]},
            index=pd.date_range("2024-01-01", periods=3),
        ),
    ],
)
def test_backtest_rejects_invalid_or_insufficient_returns(
    returns: pd.DataFrame,
) -> None:
    with pytest.raises(ValueError):
        walk_forward_backtest(
            returns,
            lambda _history: pd.Series({"a": 1.0}),
            estimation_window=2,
            rebalancing_frequency="M",
            transaction_cost_bps=0.0,
        )


def test_backtest_wraps_optimizer_errors_and_validates_proposed_weights() -> None:
    returns = pd.DataFrame(
        {"a": [0.01] * 4, "b": [0.02] * 4},
        index=pd.date_range("2024-01-01", periods=4),
    )

    def failing(_history: pd.DataFrame) -> pd.Series[float]:
        raise ValueError("private optimizer details")

    with pytest.raises(RuntimeError, match="optimizer failed") as error:
        walk_forward_backtest(
            returns,
            failing,
            estimation_window=2,
            rebalancing_frequency="M",
            transaction_cost_bps=0.0,
        )
    assert isinstance(error.value.__cause__, ValueError)

    for weights, message in (
        (pd.Series({"a": 1.0}), "must match"),
        (pd.Series({"a": float("nan"), "b": 1.0}), "non-finite"),
    ):

        def proposed_weights(
            _history: pd.DataFrame, proposed: pd.Series[float] = weights
        ) -> pd.Series[float]:
            return proposed

        with pytest.raises(RuntimeError, match=message):
            walk_forward_backtest(
                returns,
                proposed_weights,
                estimation_window=2,
                rebalancing_frequency="M",
                transaction_cost_bps=0.0,
            )


def test_backtest_accepts_optimization_result_and_rejects_nonpositive_value() -> None:
    index = pd.date_range("2024-01-01", periods=4, freq="B")
    returns = pd.DataFrame({"a": [0.01] * 4}, index=index)
    result = OptimizationResult(
        weights=pd.Series({"a": 1.0}),
        strategy="test",
        assumptions={},
        limitations=(),
    )
    backtest = walk_forward_backtest(
        returns,
        lambda _history: result,
        estimation_window=2,
        rebalancing_frequency="M",
        transaction_cost_bps=0.0,
    )
    assert backtest.weights["a"].tolist() == [1.0, 1.0]

    leveraged = pd.DataFrame(
        {"a": [-0.9, 0.0, -0.9], "b": [0.9, 0.0, 0.9]},
        index=index[:3],
    )
    with pytest.raises(RuntimeError, match="non-positive"):
        walk_forward_backtest(
            leveraged,
            lambda _history: pd.Series({"a": 2.0, "b": -1.0}),
            estimation_window=2,
            rebalancing_frequency="M",
            transaction_cost_bps=0.0,
        )
