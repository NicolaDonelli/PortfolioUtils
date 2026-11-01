"""Tests for CSV history storage."""

from datetime import date
from pathlib import Path

import pytest

from portfolio_utils.download.errors import UnexpectedResponseError
from portfolio_utils.download.models import PriceRow
from portfolio_utils.download.storage import merge_rows, read_rows, write_rows


def test_storage_writes_documented_schema_and_reads_it(tmp_path: Path) -> None:
    """CSV headers and dates follow the documented schema."""
    destination = tmp_path / "prices.csv"
    rows = [
        PriceRow(date(2024, 1, 2), 10.0, 12.0, 9.0, 11.0, 100),
        PriceRow(date(2024, 1, 3), 11.0, 13.0, 10.0, 12.0, None),
    ]

    write_rows(destination, rows)

    assert destination.read_text(encoding="utf-8") == (
        "date,open,high,low,close,volume\n"
        "2024-01-02,10.0,12.0,9.0,11.0,100\n"
        "2024-01-03,11.0,13.0,10.0,12.0,\n"
    )
    assert read_rows(destination) == rows


def test_storage_merges_with_new_rows_winning_duplicates() -> None:
    """Rows are unique and ascending after merge."""
    old = PriceRow(date(2024, 1, 2), 10.0, 12.0, 9.0, 11.0, None)
    newer = PriceRow(date(2024, 1, 2), 11.0, 13.0, 10.0, 12.0, 200)

    assert merge_rows([old], [newer]) == [newer]


def test_storage_rejects_invalid_price_ranges() -> None:
    """Invalid OHLC values are not written."""
    invalid = PriceRow(date(2024, 1, 2), 10.0, 8.0, 9.0, 11.0, None)

    with pytest.raises(UnexpectedResponseError, match="price"):
        merge_rows([], [invalid])


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (PriceRow(date(2024, 1, 2), float("nan"), 12.0, 9.0, 11.0, None), "finite"),
        (PriceRow(date(2024, 1, 2), 10.0, 12.0, 9.0, 11.0, -1), "Volume"),
    ],
)
def test_storage_rejects_nonfinite_prices_and_negative_volume(
    row: PriceRow, message: str
) -> None:
    with pytest.raises(UnexpectedResponseError, match=message):
        merge_rows([], [row])


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("day,close\n2024-01-02,11\n", "header"),
        ("date,open,high,low,close,volume\n2024-01-02,10,12,9,11\n", "row"),
        (
            "date,open,high,low,close,volume\n2024-01-02,10,12,9,11,\n"
            "2024-01-01,10,12,9,11,\n",
            "ascending",
        ),
        (
            "date,open,high,low,close,volume\nnot-a-date,10,12,9,11,\n",
            "invalid data row",
        ),
        (
            "date,open,high,low,close,volume\n2024-01-02,10,8,9,11,\n",
            "price range",
        ),
    ],
)
def test_storage_rejects_malformed_csv_records(
    tmp_path: Path, contents: str, message: str
) -> None:
    path = tmp_path / "malformed.csv"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(UnexpectedResponseError, match=message):
        read_rows(path)


def test_storage_creates_nested_destination_and_sorts_rows(tmp_path: Path) -> None:
    later = PriceRow(date(2024, 1, 3), 11.0, 13.0, 10.0, 12.0, 100)
    earlier = PriceRow(date(2024, 1, 2), 10.0, 12.0, 9.0, 11.0, 90)
    destination = tmp_path / "nested" / "prices.csv"

    write_rows(destination, [later, earlier])

    assert read_rows(destination) == [earlier, later]
