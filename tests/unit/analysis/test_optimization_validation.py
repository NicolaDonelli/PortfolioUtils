"""Input and result validation tests for portfolio optimization."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from portfolio_utils.analysis.optimization import (
    OptimizationConfig,
    OptimizationError,
    _estimate,
    _make_result,
    _validate_return_panel,
    min_volatility,
)


def _returns() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "a": [-0.02, 0.01, 0.03, -0.01],
            "b": [0.01, -0.01, 0.00, 0.02],
        },
        index=pd.date_range("2024-01-01", periods=4),
    )


@pytest.mark.parametrize(
    ("config", "message"),
    [
        (OptimizationConfig(alignment_policy="outer"), "alignment_policy"),
        (OptimizationConfig(alignment_policy="ffill"), "ffill_limit"),
        (OptimizationConfig(alignment_policy="ffill", ffill_limit=0), "ffill_limit"),
        (OptimizationConfig(ffill_limit=1), "only valid"),
        (OptimizationConfig(estimation_window=1), "estimation_window"),
        (OptimizationConfig(periods_per_year=True), "periods_per_year"),
        (OptimizationConfig(risk_free_rate=-1.0), "risk_free_rate"),
        (OptimizationConfig(rebalancing_frequency=""), "rebalancing_frequency"),
        (OptimizationConfig(transaction_cost_bps=-1.0), "transaction_cost_bps"),
        (OptimizationConfig(risk_aversion=0.0), "risk_aversion"),
        (OptimizationConfig(min_weight=0.8, max_weight=0.2), "Weight bounds"),
        (OptimizationConfig(min_weight=float("inf")), "Weight bounds"),
        (OptimizationConfig(min_weight=-0.1), "Long-only"),
        (OptimizationConfig(max_weight=1.1), "max_weight"),
        (OptimizationConfig(max_weight=0.4), "infeasible"),
        (OptimizationConfig(min_weight=0.6), "infeasible"),
    ],
)
def test_optimizer_rejects_invalid_configuration(
    config: OptimizationConfig, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        min_volatility(_returns(), config=config)


@pytest.mark.parametrize(
    ("returns", "message"),
    [
        (pd.DataFrame(), "at least one asset"),
        (
            pd.DataFrame([[0.1, 0.2]], columns=["a", "a"]),
            "unique non-empty",
        ),
        (
            pd.DataFrame([[0.1, 0.2]], columns=["a", 1]),
            "unique non-empty",
        ),
        (
            pd.DataFrame(
                {"a": [0.1, 0.2]},
                index=pd.date_range("2024-01-01", periods=2, tz="UTC"),
            ),
            "timezone-naive",
        ),
        (
            pd.DataFrame(
                {"a": [0.1, 0.2]},
                index=pd.to_datetime(["2024-01-02", "2024-01-01"]),
            ),
            "sorted, unique",
        ),
        (
            pd.DataFrame({"a": [0.1, float("inf")]}),
            "infinite values",
        ),
        (
            pd.DataFrame({"a": [0.1, -1.0]}),
            "greater than -1",
        ),
    ],
)
def test_optimizer_rejects_malformed_return_panels(
    returns: pd.DataFrame, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _validate_return_panel(returns)


def test_estimation_requires_two_complete_rows_and_uses_window() -> None:
    incomplete = pd.DataFrame({"a": [0.1, np.nan, 0.2], "b": [np.nan, 0.1, np.nan]})
    with pytest.raises(ValueError, match="two complete"):
        _estimate(incomplete, OptimizationConfig())

    estimates = _estimate(
        _returns(),
        OptimizationConfig(periods_per_year=1, estimation_window=2),
    )
    assert len(estimates.returns) == 2
    assert estimates.returns.index.tolist() == _returns().index[-2:].tolist()


@pytest.mark.parametrize(
    ("weights", "message"),
    [
        ([float("nan"), 1.0], "non-finite"),
        ([1.0], "non-finite"),
        ([0.0, 0.0], "cannot be normalized"),
        ([2.0, -1.0], "outside configured bounds"),
    ],
)
def test_optimizer_result_rejects_invalid_weights(
    weights: list[float], message: str
) -> None:
    estimates = _estimate(_returns(), OptimizationConfig())
    with pytest.raises(OptimizationError, match=message):
        _make_result(
            weights,
            estimates.returns.columns,
            "test",
            OptimizationConfig(),
            estimates,
        )
