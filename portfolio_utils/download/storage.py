"""CSV storage for daily ETF price rows."""

import csv
import math
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import IO

from portfolio_utils.download.errors import UnexpectedResponseError
from portfolio_utils.download.models import PriceRow

CSV_COLUMNS = ("date", "open", "high", "low", "close", "volume")


def _validate_row(row: PriceRow) -> None:
    """Validate fields required by the documented OHLCV schema."""
    numbers = (row.open, row.high, row.low, row.close)
    if not all(math.isfinite(value) for value in numbers):
        raise UnexpectedResponseError("Price values must be finite numbers.")
    if row.high < max(row.open, row.close, row.low) or row.low > min(
        row.open, row.close, row.high
    ):
        raise UnexpectedResponseError("OHLC price range is inconsistent.")
    if row.volume is not None and row.volume < 0:
        raise UnexpectedResponseError("Volume must be non-negative or missing.")


def merge_rows(existing: list[PriceRow], incoming: list[PriceRow]) -> list[PriceRow]:
    """Merge price rows, preferring incoming rows on duplicate dates.

    :param existing: Previously stored rows.
    :param incoming: Newly fetched rows.
    :raises UnexpectedResponseError: If a row is invalid.
    :return: Unique rows in ascending date order.
    """
    merged: dict[date, PriceRow] = {}
    try:
        for row in existing:
            _validate_row(row)
            merged[row.date] = row
        for row in incoming:
            _validate_row(row)
            merged[row.date] = row
    except UnexpectedResponseError:
        raise
    return [merged[day] for day in sorted(merged)]


def _write_csv(file: IO[str], rows: list[PriceRow]) -> None:
    writer = csv.writer(file, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        writer.writerow(
            (
                row.date.isoformat(),
                row.open,
                row.high,
                row.low,
                row.close,
                "" if row.volume is None else row.volume,
            )
        )


def write_rows(path: Path, rows: list[PriceRow]) -> None:
    """Atomically write validated rows to the documented CSV schema.

    :param path: Destination CSV path.
    :param rows: Rows to write.
    :raises UnexpectedResponseError: If a row is invalid.
    """
    try:
        ordered = merge_rows([], rows)
    except UnexpectedResponseError:
        raise
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            _write_csv(handle.file, ordered)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def read_rows(path: Path) -> list[PriceRow]:
    """Read and validate a CSV file using the documented columns.

    :param path: Source CSV path.
    :raises UnexpectedResponseError: If the header or a record is invalid.
    :return: Validated rows in file order.
    """
    rows: list[PriceRow] = []
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != list(CSV_COLUMNS):
                raise UnexpectedResponseError("CSV header does not match the schema.")
            for record in reader:
                if None in record or any(
                    record.get(column) is None for column in CSV_COLUMNS
                ):
                    raise UnexpectedResponseError("CSV row does not match the schema.")
                row = PriceRow(
                    date=date.fromisoformat(record["date"] or ""),
                    open=float(record["open"] or ""),
                    high=float(record["high"] or ""),
                    low=float(record["low"] or ""),
                    close=float(record["close"] or ""),
                    volume=None if not record["volume"] else int(record["volume"]),
                )
                _validate_row(row)
                rows.append(row)
        if merge_rows([], rows) != rows:
            raise UnexpectedResponseError(
                "CSV dates must be unique and in ascending order."
            )
    except (ValueError, KeyError, TypeError):
        raise UnexpectedResponseError("CSV contains an invalid data row.") from None
    return rows
