"""Offline tests for analysis command-line tools."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _write_prices(data_dir: Path, name: str, returns: np.ndarray) -> None:
    """Write deterministic close prices from simple returns."""
    prices = 100.0 * np.cumprod(np.concatenate(([1.0], 1.0 + returns)))
    dates = pd.bdate_range("2020-01-01", periods=len(prices))
    pd.DataFrame({"date": dates, "close": prices}).to_csv(
        data_dir / f"{name}.csv", index=False
    )


def _run_cli(
    script: str,
    arguments: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> int:
    """Run one repository CLI in-process without network access."""
    script_path = PROJECT_ROOT / "bin" / script
    monkeypatch.setattr(sys, "argv", [str(script_path), *arguments])
    try:
        runpy.run_path(str(script_path), run_name="__main__")
    except SystemExit as error:
        return int(error.code) if error.code is not None else 0
    return 0


def test_correlation_cli_selects_deterministic_low_correlation_returns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Correlation selection reports a valid subset using return correlations."""
    data_dir = tmp_path / "prices"
    data_dir.mkdir()
    first = np.array([0.01, -0.02, 0.03, -0.01, 0.02, -0.03, 0.01, -0.01])
    second = first * 2.0
    third = np.array([-0.01, -0.01, 0.02, 0.01, -0.02, 0.02, -0.01, 0.02])
    _write_prices(data_dir, "a", first)
    _write_prices(data_dir, "b", second)
    _write_prices(data_dir, "c", third)

    status = _run_cli(
        "select_uncorrelated_etfs.py",
        (
            "--data-dir",
            str(data_dir),
            "--instruments",
            "a.csv",
            "b.csv",
            "c.csv",
            "--max-abs-correlation",
            "0.4",
        ),
        monkeypatch,
    )
    output = capsys.readouterr()

    assert status == 0, output.err
    assert "simple-return correlations" in output.out.lower()
    assert "a" in output.out
    assert "c" in output.out
    assert "b" not in output.out.split("Correlation matrix", maxsplit=1)[-1]


def test_rolling_backtest_cli_reports_validation_oos_and_final_weights(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Rolling CLI emits weights, validation averages, and selected OOS metrics."""
    data_dir = tmp_path / "prices"
    data_dir.mkdir()
    dates = pd.bdate_range("2020-01-01", "2024-01-05")
    steps = np.arange(len(dates), dtype=float)
    first = 0.0002 + 0.004 * np.sin(steps * 0.31)
    second = -0.0001 + 0.003 * np.cos(steps * 0.23)
    for name, returns in (("alpha", first), ("beta", second)):
        _write_prices(data_dir, name, returns)

    status = _run_cli(
        "rolling_backtest.py",
        (
            "--data-dir",
            str(data_dir),
            "--instruments",
            "alpha.csv",
            "beta.csv",
            "--strategy",
            "hrp",
            "--train-years",
            "1",
            "--validation-years",
            "1",
            "--rolling-start",
            "2020-01-01",
            "--rolling-end",
            "2023-06-30",
            "--oos-start",
            "2023-07-03",
            "--oos-end",
            "2023-12-29",
            "--metrics",
            "cumulative_return,sharpe_ratio",
        ),
        monkeypatch,
    )
    output = capsys.readouterr()

    assert status == 0, output.err
    assert "Final portfolio weights" in output.out
    assert "Validation-window metric averages" in output.out
    assert "Out-of-sample metrics" in output.out
    assert "alpha" in output.out
    assert "beta" in output.out
    assert "cumulative_return" in output.out
    assert "sharpe_ratio" in output.out
    assert "annualized_realized_volatility" not in output.out


def test_rolling_backtest_requires_target_for_targeted_strategy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Strategies without an API target default fail with an explicit message."""
    status = _run_cli(
        "rolling_backtest.py",
        ("--data-dir", str(tmp_path), "--strategy", "efficient_return"),
        monkeypatch,
    )
    output = capsys.readouterr()

    assert status == 2
    assert "--target-return is required" in output.err
