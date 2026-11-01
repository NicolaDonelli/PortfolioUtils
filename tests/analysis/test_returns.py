"""Tests for loading price panels and computing returns."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, cast

import numpy as np
import pandas as pd
import pytest

from portfolio_utils.analysis.loading import load_price_data, load_price_panel
from portfolio_utils.analysis.returns import align_prices, prices_to_returns


def _write_prices(path: Path, rows: list[tuple[str, float]]) -> None:
    lines = ["date,close"]
    lines.extend(f"{day},{price}" for day, price in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_loads_close_prices_and_metadata_from_csv(tmp_path: Path) -> None:
    _write_prices(
        tmp_path / "asset_a.csv",
        [("2024-01-02", 100.0), ("2024-01-03", 110.0)],
    )
    (tmp_path / "asset_a.meta.json").write_text(
        '{"currency":"EUR","distributing":false,"dividend_adjusted":true}',
        encoding="utf-8",
    )

    data = load_price_data(tmp_path)

    assert data.prices.columns.tolist() == ["asset_a"]
    assert data.prices.index.is_monotonic_increasing
    assert data.metadata["asset_a"].currency == "EUR"
    assert data.metadata["asset_a"].dividend_adjusted is True
    assert data.metadata["asset_a"].distributing is False
    assert "survivorship" in " ".join(data.limitations).lower()


def test_load_price_panel_can_select_instruments(tmp_path: Path) -> None:
    _write_prices(tmp_path / "a.csv", [("2024-01-01", 100.0)])
    _write_prices(tmp_path / "b.csv", [("2024-01-01", 200.0)])

    panel = load_price_panel(tmp_path, instruments=["b"])

    assert panel.columns.tolist() == ["b"]
    assert panel.iloc[0, 0] == pytest.approx(200.0)


def test_loader_rejects_mixed_known_currencies(tmp_path: Path) -> None:
    _write_prices(tmp_path / "a.csv", [("2024-01-01", 100.0)])
    _write_prices(tmp_path / "b.csv", [("2024-01-01", 200.0)])
    (tmp_path / "a.meta.json").write_text('{"currency":"EUR"}', encoding="utf-8")
    (tmp_path / "b.meta.json").write_text('{"currency":"USD"}', encoding="utf-8")

    with pytest.raises(ValueError, match="different currencies"):
        load_price_data(tmp_path)


def test_loader_rejects_bad_schema_and_empty_selection(tmp_path: Path) -> None:
    (tmp_path / "broken.csv").write_text("date,open\n2024-01-01,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="date and close"):
        load_price_panel(tmp_path)
    (tmp_path / "empty").mkdir()
    with pytest.raises(ValueError, match="No CSV price files"):
        load_price_panel(tmp_path / "empty")


def test_inner_alignment_and_forward_fill_are_explicit() -> None:
    index = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
    prices = pd.DataFrame(
        {"a": [100.0, 110.0, 121.0], "b": [200.0, np.nan, 220.0]}, index=index
    )

    inner = align_prices(prices, policy="inner")
    carried = align_prices(prices, policy="ffill", limit=1)

    assert inner.index.tolist() == [index[0], index[2]]
    assert carried.loc[index[1], "b"] == pytest.approx(200.0)
    assert carried.loc[index[2], "b"] == pytest.approx(220.0)
    with pytest.raises(ValueError, match="limit"):
        align_prices(prices, policy="ffill")


def test_returns_are_vectorized_and_do_not_fill_missing_prices() -> None:
    index = pd.date_range("2024-01-01", periods=3, freq="D")
    prices = pd.DataFrame({"a": [100.0, 110.0, 99.0]}, index=index)

    simple = prices_to_returns(prices, method="simple")
    log = prices_to_returns(prices, method="log")

    np.testing.assert_allclose(simple["a"].to_numpy(), [0.1, -0.1])
    np.testing.assert_allclose(log["a"].to_numpy(), np.log(np.array([1.1, 0.9])))
    assert simple.index[0] == index[1]
    with pytest.raises(ValueError, match="positive"):
        prices_to_returns(prices.assign(a=[100.0, 0.0, 99.0]), method="simple")


def test_align_validates_index_and_rejects_backfill_policy() -> None:
    unsorted = pd.DataFrame(
        {"a": [1.0, 2.0]},
        index=pd.to_datetime(["2024-01-02", "2024-01-01"]),
    )
    with pytest.raises(ValueError, match="sorted"):
        align_prices(unsorted, policy="inner")
    with pytest.raises(ValueError, match="policy"):
        align_prices(unsorted.sort_index(), policy="backfill")


def test_alignment_rejects_conflicting_limits_and_empty_calendars() -> None:
    index = pd.date_range("2024-01-01", periods=2)
    prices = pd.DataFrame({"a": [100.0, np.nan]}, index=index)

    with pytest.raises(ValueError, match="only valid"):
        align_prices(prices, policy="inner", limit=1)
    with pytest.raises(ValueError, match="positive limit"):
        align_prices(prices, policy="ffill", limit=0)
    with pytest.raises(ValueError, match="no complete"):
        align_prices(
            pd.DataFrame(
                {"a": [100.0, np.nan], "b": [np.nan, 200.0]},
                index=index,
            ),
            policy="inner",
        )


def test_prices_to_returns_rejects_invalid_method_and_short_calendar() -> None:
    prices = pd.DataFrame(
        {"a": [100.0, 110.0]},
        index=pd.date_range("2024-01-01", periods=2),
    )
    with pytest.raises(ValueError, match="method"):
        prices_to_returns(prices, method=cast(Literal["simple", "log"], "compound"))
    with pytest.raises(ValueError, match="At least two aligned prices"):
        prices_to_returns(
            pd.DataFrame(
                {"a": [100.0, np.nan]},
                index=pd.date_range("2024-01-01", periods=2),
            )
        )
