"""Hand-computed examples and edge cases for performance statistics."""

from __future__ import annotations

from typing import cast

import numpy as np
import pandas as pd
import pytest

from portfolio_utils.analysis.metrics import (
    PerformanceAssumptions,
    annualized_realized_volatility,
    annualized_return,
    annualized_sharpe_ratio,
    annualized_sortino_ratio,
    annualized_volatility,
    beta,
    cagr,
    calmar_ratio,
    cumulative_return,
    historical_cvar,
    historical_var,
    information_ratio,
    max_drawdown,
    performance_summary,
    realized_volatility,
    sharpe_ratio,
    sortino_ratio,
    tracking_error,
)


def test_basic_metrics_match_two_return_hand_calculation() -> None:
    returns = pd.Series([0.1, -0.1], dtype=float)
    prices = pd.Series(
        [100.0, 110.0, 99.0],
        index=pd.date_range("2024-01-01", periods=3, freq="D"),
        dtype=float,
    )

    assert cumulative_return(returns) == pytest.approx(-0.01)
    assert annualized_return(returns, periods_per_year=2) == pytest.approx(0.0)
    assert annualized_volatility(returns, periods_per_year=2) == pytest.approx(0.2)
    assert sharpe_ratio(
        returns, periods_per_year=2, risk_free_rate=0.0
    ) == pytest.approx(0.0)
    assert max_drawdown(prices) == pytest.approx(-0.1)


def test_annualized_metrics_scale_period_metrics() -> None:
    returns = pd.Series([0.02, -0.01, 0.03], dtype=float)
    periods_per_year = 4

    assert annualized_sharpe_ratio(
        returns, periods_per_year=periods_per_year, risk_free_rate=0.0
    ) == pytest.approx(
        sharpe_ratio(returns, periods_per_year=periods_per_year, risk_free_rate=0.0)
        * np.sqrt(periods_per_year)
    )
    assert annualized_sortino_ratio(
        returns, periods_per_year=periods_per_year, risk_free_rate=0.0
    ) == pytest.approx(
        sortino_ratio(returns, periods_per_year=periods_per_year, risk_free_rate=0.0)
        * np.sqrt(periods_per_year)
    )
    assert realized_volatility(returns) == pytest.approx(returns.std(ddof=1))
    assert annualized_realized_volatility(
        returns, periods_per_year=periods_per_year
    ) == pytest.approx(returns.std(ddof=1) * np.sqrt(periods_per_year))


def test_downside_and_drawdown_metrics() -> None:
    returns = pd.Series([-0.1, 0.1], dtype=float)
    prices = pd.Series(
        [100.0, 120.0, 110.0],
        index=pd.to_datetime(["2023-01-01", "2023-07-01", "2024-01-01"]),
        dtype=float,
    )

    assert sortino_ratio(
        returns, periods_per_year=2, risk_free_rate=0.0
    ) == pytest.approx(0.0)
    assert cagr(prices) == pytest.approx(0.1, rel=0.001)
    assert calmar_ratio(prices) == pytest.approx(1.2, rel=0.01)


def test_benchmark_and_tail_metrics_are_hand_checkable() -> None:
    asset = pd.Series([0.0, 0.1, -0.1, 0.0], dtype=float)
    benchmark = pd.Series([0.0, 0.05, -0.05, 0.0], dtype=float)

    assert beta(asset, benchmark, alignment="exact") == pytest.approx(2.0)
    assert tracking_error(asset, benchmark, periods_per_year=2) == pytest.approx(
        np.std([0.0, 0.05, -0.05, 0.0], ddof=1) * np.sqrt(2.0)
    )
    assert information_ratio(asset, benchmark, periods_per_year=2) == pytest.approx(0.0)
    assert historical_var(
        pd.Series([-0.2, -0.1, 0.0, 0.1]), alpha=0.75
    ) == pytest.approx(0.125)
    assert historical_cvar(
        pd.Series([-0.2, -0.1, 0.0, 0.1]), alpha=0.75
    ) == pytest.approx(0.2)


def test_metrics_reject_invalid_or_undefined_inputs() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        annualized_volatility(pd.Series([0.1]), periods_per_year=252)
    with pytest.raises(ValueError, match="greater than -1"):
        cumulative_return(pd.Series([-1.0, 0.1]))
    with pytest.raises(ValueError, match="zero volatility"):
        sharpe_ratio(pd.Series([0.0, 0.0]), periods_per_year=252, risk_free_rate=0.0)
    with pytest.raises(ValueError, match="downside"):
        sortino_ratio(pd.Series([0.1, 0.2]), periods_per_year=252, risk_free_rate=0.0)
    with pytest.raises(ValueError, match="drawdown"):
        calmar_ratio(
            pd.Series(
                [100.0, 110.0],
                index=pd.date_range("2024-01-01", periods=2),
                dtype=float,
            )
        )
    with pytest.raises(ValueError, match="alignment"):
        beta(
            pd.Series([0.1, 0.2], index=[1, 2], dtype=float),
            pd.Series([0.1, 0.2], index=[2, 3], dtype=float),
            alignment="exact",
        )


def test_summary_includes_assumptions_and_limitations() -> None:
    prices = pd.DataFrame(
        {"a": [100.0, 101.0, 99.99, 101.9898, 101.9898]},
        index=pd.date_range("2024-01-01", periods=5, freq="D"),
    )
    summary = performance_summary(
        prices,
        assumptions=PerformanceAssumptions(
            periods_per_year=252,
            risk_free_rate=0.02,
            alignment_policy="inner",
            currency="EUR",
            dividend_adjusted=False,
        ),
    )

    assert summary.loc["a", "sharpe_ratio"] == pytest.approx(
        sharpe_ratio(
            prices["a"].pct_change().dropna(),
            periods_per_year=252,
            risk_free_rate=0.02,
        )
    )
    assert {
        "sharpe_ratio",
        "annualized_sharpe_ratio",
        "sortino_ratio",
        "annualized_sortino_ratio",
        "annualized_return",
        "cumulative_return",
        "realized_volatility",
        "annualized_realized_volatility",
    } == set(summary.columns)
    assert summary.attrs["assumptions"]["alignment_policy"] == "inner"
    assert any(
        "past performance" in item.lower() for item in summary.attrs["limitations"]
    )


def test_metrics_reject_invalid_annualization_and_rates() -> None:
    returns = pd.Series([0.1, -0.1])
    for periods_per_year in (0, True):
        with pytest.raises(ValueError, match="positive integer"):
            annualized_return(returns, periods_per_year=periods_per_year)
    with pytest.raises(ValueError, match="risk_free"):
        sharpe_ratio(returns, periods_per_year=2, risk_free_rate=-1.0)
    with pytest.raises(ValueError, match="risk_free"):
        sortino_ratio(returns, periods_per_year=2, risk_free_rate=float("nan"))


def test_price_metrics_validate_dates_span_and_values() -> None:
    same_day = pd.Series(
        [100.0, 101.0],
        index=pd.to_datetime(["2024-01-01 00:00", "2024-01-01 12:00"]),
    )
    with pytest.raises(ValueError, match="positive calendar-day span"):
        cagr(same_day)

    with pytest.raises(ValueError, match="At least two prices"):
        max_drawdown(pd.Series([100.0], index=pd.to_datetime(["2024-01-01"])))
    with pytest.raises(ValueError, match="timezone-naive"):
        max_drawdown(
            pd.Series(
                [100.0, 101.0],
                index=pd.date_range("2024-01-01", periods=2, tz="UTC"),
            )
        )
    with pytest.raises(ValueError, match="finite"):
        cagr(
            pd.Series(
                [100.0, float("inf")],
                index=pd.date_range("2024-01-01", periods=2),
            )
        )
    with pytest.raises(ValueError, match="positive"):
        cagr(
            pd.Series(
                [100.0, 0.0],
                index=pd.date_range("2024-01-01", periods=2),
            )
        )


def test_relative_metrics_reject_undefined_alignment_and_variance() -> None:
    asset = pd.Series([0.1, 0.2], index=[1, 2], dtype=float)
    benchmark = pd.Series([0.1, 0.2], index=[1, 2], dtype=float)
    with pytest.raises(ValueError, match="alignment"):
        beta(asset, benchmark, alignment="outer")
    with pytest.raises(ValueError, match="benchmark variance"):
        beta(asset, pd.Series([0.1, 0.1], index=[1, 2]), alignment="exact")
    with pytest.raises(ValueError, match="at least 2"):
        beta(
            pd.Series([0.1], index=[1]),
            pd.Series([0.0], index=[1]),
            alignment="inner",
        )
    with pytest.raises(ValueError, match="indexes must match"):
        tracking_error(
            pd.Series([0.1, 0.2], index=[1, 2]),
            pd.Series([0.1, 0.2], index=[2, 3]),
            periods_per_year=252,
        )
    with pytest.raises(ValueError, match="at least 2"):
        tracking_error(
            pd.Series([0.1], dtype=float),
            pd.Series([0.0], dtype=float),
            periods_per_year=252,
        )
    with pytest.raises(ValueError, match="zero tracking error"):
        information_ratio(
            pd.Series([0.1, 0.2], dtype=float),
            pd.Series([0.1, 0.2], dtype=float),
            periods_per_year=252,
        )


def test_tail_metrics_validate_confidence_and_report_undefined_summary_ratios() -> None:
    returns = pd.Series([-0.1, 0.1], dtype=float)
    for alpha in (0.0, 1.0, float("nan")):
        with pytest.raises(ValueError, match="alpha"):
            historical_var(returns, alpha=alpha)
        with pytest.raises(ValueError, match="alpha"):
            historical_cvar(returns, alpha=alpha)

    flat_prices = pd.DataFrame(
        {"flat": [100.0, 100.0, 100.0]},
        index=pd.date_range("2024-01-01", periods=3),
    )
    summary = performance_summary(
        flat_prices,
        assumptions=PerformanceAssumptions(
            periods_per_year=252,
            risk_free_rate=0.0,
            alignment_policy="inner",
            currency=None,
            dividend_adjusted=None,
        ),
    )
    assert np.isnan(cast(float, summary.loc["flat", "sharpe_ratio"]))
    assert np.isnan(cast(float, summary.loc["flat", "sortino_ratio"]))
    assert any(
        "Currency was not supplied" in item for item in summary.attrs["limitations"]
    )
    assert any("not confirmed" in item for item in summary.attrs["limitations"])


def test_performance_summary_uses_bounded_forward_fill() -> None:
    index = pd.date_range("2024-01-01", periods=3)
    prices = pd.DataFrame(
        {"a": [100.0, 110.0, 121.0], "b": [200.0, np.nan, 220.0]},
        index=index,
    )
    result = performance_summary(
        prices,
        assumptions=PerformanceAssumptions(
            periods_per_year=252,
            risk_free_rate=0.0,
            alignment_policy="ffill",
            currency="USD",
            dividend_adjusted=True,
            ffill_limit=1,
        ),
    )

    assert result.attrs["period"] == ("2024-01-01", "2024-01-03")
    assert result.attrs["assumptions"]["ffill_limit"] == 1
