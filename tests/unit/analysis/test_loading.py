"""Offline tests for CSV price loading and metadata sidecars."""

from __future__ import annotations

from pathlib import Path

import pytest

from portfolio_utils.analysis.loading import (
    InstrumentMetadata,
    _read_metadata,
    load_price_data,
)


def _csv(path: Path, contents: str = "date,close\n2024-01-01,100\n") -> None:
    path.write_text(contents, encoding="utf-8")


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("{", "Unable to read metadata"),
        ("[]", "JSON object"),
        ('{"currency":""}', "currency"),
        ('{"distributing":"yes"}', "distributing"),
        ('{"dividend_adjusted":1}', "adjustment"),
    ],
)
def test_metadata_sidecar_rejects_malformed_content(
    tmp_path: Path, contents: str, message: str
) -> None:
    csv_path = tmp_path / "asset.csv"
    csv_path.touch()
    csv_path.with_suffix(".meta.json").write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        _read_metadata(csv_path)


def test_metadata_supports_alternate_sidecar_and_adjustment_field(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "asset.csv"
    csv_path.touch()
    Path(f"{csv_path}.meta.json").write_text(
        '{"currency":"usd","adjusted_close":true}', encoding="utf-8"
    )

    assert _read_metadata(csv_path) == InstrumentMetadata("usd", None, True, True)


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("date,open\n2024-01-01,100\n", "date and close"),
        ("date,close\nnot-a-date,100\n", "invalid date or close"),
        ("date,close\n2024-01-01T00:00:00+00:00,100\n", "timezone-naive"),
        (
            "date,close\n2024-01-02,100\n2024-01-01,101\n",
            "sorted in ascending",
        ),
        (
            "date,close\n2024-01-01,100\n2024-01-01,101\n",
            "unique",
        ),
        ("date,close\n2024-01-01,\n", "missing close"),
        ("date,close\n2024-01-01,0\n", "positive"),
    ],
)
def test_loader_rejects_invalid_price_files(
    tmp_path: Path, contents: str, message: str
) -> None:
    _csv(tmp_path / "asset.csv", contents)

    with pytest.raises(ValueError, match=message):
        load_price_data(tmp_path)


def test_loader_rejects_missing_directory_and_invalid_selections(
    tmp_path: Path,
) -> None:
    with pytest.raises(FileNotFoundError, match="does not exist"):
        load_price_data(tmp_path / "missing")

    _csv(tmp_path / "asset.csv")
    with pytest.raises(ValueError, match="at least one"):
        load_price_data(tmp_path, instruments=[])
    with pytest.raises(ValueError, match="duplicate"):
        load_price_data(tmp_path, instruments=["asset", "asset"])
    with pytest.raises(ValueError, match="No CSV price file found"):
        load_price_data(tmp_path, instruments=["unknown"])


def test_loader_reports_unknown_data_and_can_allow_mixed_currencies(
    tmp_path: Path,
) -> None:
    _csv(tmp_path / "euro.csv")
    _csv(tmp_path / "dollar.csv")
    (tmp_path / "euro.meta.json").write_text(
        '{"currency":"EUR","distributing":true}', encoding="utf-8"
    )
    (tmp_path / "dollar.meta.json").write_text(
        '{"currency":"USD","dividend_adjusted":false}', encoding="utf-8"
    )

    with pytest.raises(ValueError, match="different currencies"):
        load_price_data(tmp_path)
    loaded = load_price_data(tmp_path, allow_mixed_currencies=True)

    assert loaded.prices.columns.tolist() == ["dollar", "euro"]
    assert loaded.prices.notna().all().all()
    limitations = " ".join(loaded.limitations)
    assert "Mixed currencies" in limitations
    assert "Distributing share classes" in limitations
    assert "Dividend adjustment is unverified for: euro" in limitations


def test_loader_handles_unknown_currency_and_directory_csv_read_failure(
    tmp_path: Path,
) -> None:
    _csv(tmp_path / "asset.csv")
    loaded = load_price_data(tmp_path)
    assert "Currency is unknown for: asset" in " ".join(loaded.limitations)

    broken = tmp_path / "broken.csv"
    broken.mkdir()
    with pytest.raises(ValueError, match="Unable to read price file"):
        load_price_data(tmp_path)
