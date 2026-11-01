"""Offline synthetic tests for portfolio optimizers."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from portfolio_utils.analysis.optimization import (
    BlackLittermanInputs,
    OptimizationConfig,
    efficient_cvar,
    efficient_return,
    efficient_risk,
    efficient_semivariance,
    max_quadratic_utility,
    max_sharpe,
    min_cvar,
    min_semivariance,
    min_volatility,
    optimize_black_litterman,
    optimize_hrp,
)


@pytest.fixture
def returns() -> pd.DataFrame:
    """Deterministic, correlated simple returns with two assets."""
    index = pd.date_range("2024-01-01", periods=12, freq="B")
    first = np.array(
        [-0.02, 0.01, 0.03, -0.01, 0.02, 0.00, -0.03, 0.04, 0.01, -0.01, 0.02, 0.03]
    )
    second = np.array(
        [0.01, -0.01, 0.00, 0.02, -0.02, 0.03, 0.01, -0.01, 0.02, 0.00, 0.01, -0.01]
    )
    return pd.DataFrame({"a": first, "b": second}, index=index)


def test_frontier_strategies_return_normalized_bounded_weights(
    returns: pd.DataFrame,
) -> None:
    config = OptimizationConfig(
        periods_per_year=252,
        risk_free_rate=0.01,
        max_weight=0.8,
        solver="CLARABEL",
    )
    strategies = [
        min_volatility(returns, config=config),
        max_sharpe(returns, config=config),
        max_quadratic_utility(returns, config=config),
        efficient_risk(returns, config=config, target_volatility=0.2),
        efficient_return(returns, config=config, target_return=0.01),
        min_cvar(returns, config=config, beta=0.8),
        efficient_cvar(returns, config=config, target_return=0.01, beta=0.8),
        min_semivariance(returns, config=config),
        efficient_semivariance(returns, config=config, target_return=0.01),
        optimize_hrp(returns, config=config),
    ]

    for result in strategies:
        assert result.weights.sum() == pytest.approx(1.0, abs=1e-8)
        assert result.weights.min() >= -1e-8
        assert result.weights.max() <= 0.8 + 1e-8
        assert result.weights.notna().all()
        assert "past performance" in " ".join(result.limitations).lower()


def test_two_uncorrelated_assets_minimum_variance_is_inverse_variance() -> None:
    returns = pd.DataFrame(
        {
            "low_vol": [-0.01, 0.01, -0.01, 0.01],
            "high_vol": [-0.02, -0.02, 0.02, 0.02],
        }
    )

    result = min_volatility(
        returns, config=OptimizationConfig(periods_per_year=1, solver="CLARABEL")
    )

    assert result.weights["low_vol"] == pytest.approx(0.8, abs=1e-4)
    assert result.weights["high_vol"] == pytest.approx(0.2, abs=1e-4)


def test_black_litterman_requires_explicit_prior_and_views(
    returns: pd.DataFrame,
) -> None:
    config = OptimizationConfig(periods_per_year=252)
    with pytest.raises(ValueError, match="views"):
        optimize_black_litterman(
            returns,
            config=config,
            inputs=BlackLittermanInputs(
                market_caps=pd.Series({"a": 100.0, "b": 100.0})
            ),
        )
    with pytest.raises(ValueError, match="market_caps or prior_returns"):
        optimize_black_litterman(
            returns,
            config=config,
            inputs=BlackLittermanInputs(absolute_views=pd.Series({"a": 0.05})),
        )


def test_black_litterman_uses_supplied_absolute_views(
    returns: pd.DataFrame,
) -> None:
    result = optimize_black_litterman(
        returns,
        config=OptimizationConfig(periods_per_year=252, risk_aversion=1.0),
        inputs=BlackLittermanInputs(
            market_caps=pd.Series({"a": 100.0, "b": 100.0}),
            absolute_views=pd.Series({"a": 0.05}),
        ),
    )

    assert result.weights.sum() == pytest.approx(1.0, abs=1e-8)
    assert result.assumptions["views"] == "absolute"


def test_optimizer_validates_target_bounds_and_data(
    returns: pd.DataFrame,
) -> None:
    config = OptimizationConfig(periods_per_year=252)
    with pytest.raises(ValueError, match="target_return"):
        efficient_return(returns, config=config, target_return=float("nan"))
    with pytest.raises(ValueError, match="bounds"):
        min_volatility(
            returns, config=OptimizationConfig(periods_per_year=252, max_weight=0.2)
        )
    with pytest.raises(ValueError, match="complete return"):
        min_volatility(
            returns.assign(a=np.nan),
            config=config,
        )


def test_estimation_window_is_explicit_and_recorded(
    returns: pd.DataFrame,
) -> None:
    result = min_volatility(
        returns,
        config=OptimizationConfig(
            periods_per_year=252,
            estimation_window=6,
            rebalancing_frequency="M",
            transaction_cost_bps=10.0,
        ),
    )

    assert result.assumptions["estimation_observations"] == 6
    assert result.assumptions["rebalancing_frequency"] == "M"
    assert result.assumptions["transaction_cost_bps"] == 10.0
