"""Template for a PortfolioUtils test module (copy, rename and adapt)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

# from portfolio_utils.analysis.metrics import max_drawdown


@pytest.fixture
def prices() -> pd.Series[float]:
    """Small hand-checked price series."""
    index = pd.date_range("2024-01-01", periods=5, freq="B")
    return pd.Series([100.0, 110.0, 99.0, 105.0, 120.0], index=index, name="etf_a")


def test_max_drawdown_returns_peak_to_trough_loss(prices: pd.Series[float]) -> None:
    expected = 99.0 / 110.0 - 1.0
    # assert max_drawdown(prices) == pytest.approx(expected)
    assert expected < 0


@pytest.mark.parametrize("n_rows", [0, 1])
def test_max_drawdown_rejects_too_short_series(n_rows: int) -> None:
    short = pd.Series([100.0] * n_rows, dtype=float)
    assert len(short) == n_rows
    # with pytest.raises(InsufficientDataError, match="at least two"):
    #     max_drawdown(short)


def test_csv_is_written_in_tmp_path_only(tmp_path: Path) -> None:
    target = tmp_path / "etf_a.csv"
    target.write_text("date,close\n2024-01-01,100.0\n", encoding="utf-8")
    assert target.exists()


def test_settings_read_fake_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INVESTING_EMAIL", "user@example.com")
    monkeypatch.setenv("INVESTING_PASSWORD", "not-a-real-password")  # pragma: allowlist secret
    # settings = Settings()
    # assert "not-a-real-password" not in repr(settings)
