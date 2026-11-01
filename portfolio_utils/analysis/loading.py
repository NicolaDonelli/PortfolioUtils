"""Read-only loading of close-price CSV files and their metadata sidecars."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from portfolio_utils.analysis._validation import validate_price_panel


@dataclass(frozen=True)
class InstrumentMetadata:
    """Currency and dividend-treatment information for one instrument.

    :ivar currency: Trading currency, or ``None`` if metadata is unavailable.
    :ivar distributing: Whether the share class distributes dividends, if known.
    :ivar dividend_adjusted: Whether the price history includes reinvested
        dividends, if known.
    :ivar metadata_available: Whether a metadata sidecar was present.
    """

    currency: str | None
    distributing: bool | None
    dividend_adjusted: bool | None
    metadata_available: bool


@dataclass(frozen=True)
class PriceData:
    """Price panel together with per-instrument metadata and known limitations.

    :ivar prices: Wide close-price panel indexed by trading date.
    :ivar metadata: Metadata indexed by the matching panel column.
    :ivar limitations: Data and inference limitations to retain in reports.
    """

    prices: pd.DataFrame
    metadata: dict[str, InstrumentMetadata]
    limitations: tuple[str, ...]


def _read_metadata(csv_path: Path) -> InstrumentMetadata:
    """Read an optional JSON sidecar for one CSV.

    :param csv_path: Price CSV path.
    :raises ValueError: If a sidecar is malformed or has invalid field types.
    :return: Parsed metadata, with unknown fields represented by ``None``.
    """
    sidecar_candidates = (
        csv_path.with_suffix(".meta.json"),
        Path(f"{csv_path}.meta.json"),
    )
    sidecar = next((path for path in sidecar_candidates if path.is_file()), None)
    if sidecar is None:
        return InstrumentMetadata(None, None, None, False)
    try:
        raw: Any = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Unable to read metadata sidecar {sidecar.name}.") from error
    if not isinstance(raw, dict):
        raise ValueError(f"Metadata sidecar {sidecar.name} must contain a JSON object.")

    currency = raw.get("currency")
    if currency is not None and (not isinstance(currency, str) or not currency.strip()):
        raise ValueError(
            f"Metadata currency in {sidecar.name} must be a non-empty string."
        )
    distributing = raw.get("distributing")
    adjusted = raw.get(
        "dividend_adjusted",
        raw.get("adjusted_close", raw.get("prices_dividend_adjusted")),
    )
    if distributing is not None and not isinstance(distributing, bool):
        raise ValueError(f"Metadata distributing in {sidecar.name} must be boolean.")
    if adjusted is not None and not isinstance(adjusted, bool):
        raise ValueError(f"Dividend adjustment in {sidecar.name} must be boolean.")
    return InstrumentMetadata(currency, distributing, adjusted, True)


def _read_close_prices(path: Path) -> pd.Series[float]:
    """Read one CSV and validate its date and close columns.

    :param path: Source CSV path.
    :raises ValueError: If required columns or valid observations are missing.
    :return: Positive close prices indexed by date.
    """
    frame = _read_csv(path)
    if not {"date", "close"}.issubset(frame.columns):
        raise ValueError(f"Price file {path.name} must contain date and close columns.")
    dates, close = _parse_dates_and_close(frame, path)
    if not dates.is_monotonic_increasing:
        raise ValueError(f"Dates in {path.name} must be sorted in ascending order.")
    if not dates.is_unique:
        raise ValueError(f"Dates in {path.name} must be unique.")
    if close.isna().any():
        raise ValueError(f"Price file {path.name} contains missing close prices.")
    series = pd.Series(close.to_numpy(), index=dates, name=path.stem, dtype=float)
    validate_price_panel(series.to_frame())
    return series


def _read_csv(path: Path) -> pd.DataFrame:
    """Read one CSV while translating parser and filesystem failures.

    :param path: Source CSV path.
    :raises ValueError: If the file cannot be read.
    :return: Parsed CSV records.
    """
    try:
        return pd.read_csv(path)
    except (OSError, pd.errors.ParserError) as error:
        raise ValueError(f"Unable to read price file {path.name}.") from error


def _parse_dates_and_close(
    frame: pd.DataFrame, path: Path
) -> tuple[pd.DatetimeIndex, pd.Series[float]]:
    """Parse date and numeric close columns from CSV records.

    :param frame: Records parsed from one CSV.
    :param path: Source file used in validation messages.
    :raises ValueError: If values are malformed or dates are timezone-aware.
    :return: Parsed date index and close values.
    """
    try:
        dates = pd.DatetimeIndex(pd.to_datetime(frame["date"], errors="raise"))
        close = pd.to_numeric(frame["close"], errors="raise").astype(float)
    except (TypeError, ValueError, pd.errors.OutOfBoundsDatetime) as error:
        raise ValueError(
            f"Price file {path.name} has invalid date or close values."
        ) from error
    if dates.tz is not None:
        raise ValueError(f"Price file {path.name} must use timezone-naive dates.")
    return dates, close


def _select_price_paths(
    data_dir: Path, instruments: list[str] | tuple[str, ...] | None
) -> list[Path]:
    """Select CSVs, enforcing exact requested filename stems.

    :param data_dir: Input directory.
    :param instruments: Optional exact filename stems.
    :raises FileNotFoundError: If the directory is absent.
    :raises ValueError: If selection is empty or includes unknown stems.
    :return: Selected CSV paths.
    """
    if not data_dir.is_dir():
        raise FileNotFoundError(f"Price-data directory does not exist: {data_dir}")
    paths = sorted(data_dir.glob("*.csv"))
    if instruments is None:
        if not paths:
            raise ValueError(f"No CSV price files found in {data_dir}.")
        return paths
    if not instruments:
        raise ValueError("instruments must select at least one CSV file.")
    if len(set(instruments)) != len(instruments):
        raise ValueError("instruments must not contain duplicate names.")
    path_by_stem = {path.stem: path for path in paths}
    missing = sorted(set(instruments).difference(path_by_stem))
    if missing:
        raise ValueError(f"No CSV price file found for: {', '.join(missing)}.")
    return [path_by_stem[instrument] for instrument in instruments]


def _validate_currencies(
    metadata: dict[str, InstrumentMetadata], allow_mixed_currencies: bool
) -> None:
    """Reject known currency mixing unless explicitly allowed.

    :param metadata: Instrument metadata to check.
    :param allow_mixed_currencies: Whether known mismatches are allowed.
    :raises ValueError: If multiple known currencies are present without consent.
    """
    currencies = {
        item.currency.upper() for item in metadata.values() if item.currency is not None
    }
    if len(currencies) > 1 and not allow_mixed_currencies:
        raise ValueError(
            "Selected instruments use different currencies; convert them to a "
            "common currency or explicitly set allow_mixed_currencies=True."
        )


def _limitations(
    metadata: dict[str, InstrumentMetadata], allow_mixed_currencies: bool
) -> tuple[str, ...]:
    """Build analysis caveats for the loaded data.

    :param metadata: Metadata loaded for each instrument.
    :param allow_mixed_currencies: Whether multiple currencies were permitted.
    :return: Caveats to accompany results.
    """
    items = [
        "CSV close prices may not include reinvested dividends; confirm "
        "dividend-adjusted treatment before comparing total returns.",
        "Short ETF histories and omitted/delisted instruments can create "
        "survivorship and selection bias.",
        "Past performance does not predict future returns.",
    ]
    unknown_currency = [
        name for name, item in metadata.items() if item.currency is None
    ]
    if unknown_currency:
        items.append("Currency is unknown for: " + ", ".join(unknown_currency) + ".")
    unknown_adjustment = [
        name for name, item in metadata.items() if item.dividend_adjusted is None
    ]
    if unknown_adjustment:
        items.append(
            "Dividend adjustment is unverified for: "
            + ", ".join(unknown_adjustment)
            + "."
        )
    distributing = [
        name for name, item in metadata.items() if item.distributing is True
    ]
    if distributing:
        items.append(
            "Distributing share classes may omit cash distributions from price returns: "
            + ", ".join(distributing)
            + "."
        )
    currencies = {
        item.currency.upper() for item in metadata.values() if item.currency is not None
    }
    if allow_mixed_currencies and len(currencies) > 1:
        items.append(
            "Mixed currencies were explicitly allowed but no FX conversion was applied."
        )
    return tuple(items)


def load_price_data(
    data_dir: Path = Path("data"),
    *,
    instruments: list[str] | tuple[str, ...] | None = None,
    allow_mixed_currencies: bool = False,
) -> PriceData:
    """Load selected CSV close prices and metadata without changing source files.

    Filenames without the ``.csv`` suffix become instrument slugs. The loader
    accepts either ``slug.meta.json`` or ``slug.csv.meta.json`` sidecars. It
    returns the union calendar; call :func:`align_prices` before comparisons
    or portfolio simulations.

    :param data_dir: Directory containing source CSV files.
    :param instruments: Optional exact filename stems to include.
    :param allow_mixed_currencies: Explicitly permit known currency mismatches.
    :return: Price panel, instrument metadata, and analysis limitations.

    >>> from pathlib import (
    ...     Path,
    ... )
    >>> prices = load_price_data(
    ...     Path("data"),
    ...     instruments=[],
    ... )
    Traceback (most recent call last):
    ...
    ValueError: instruments must select at least one CSV file.
    """
    paths = _select_price_paths(data_dir, instruments)
    series_by_name: dict[str, pd.Series[float]] = {}
    metadata: dict[str, InstrumentMetadata] = {}
    for path in paths:
        series_by_name[path.stem] = _read_close_prices(path)
        metadata[path.stem] = _read_metadata(path)
    prices = pd.concat(series_by_name, axis=1).sort_index()
    prices.columns = list(series_by_name)
    validate_price_panel(prices)
    _validate_currencies(metadata, allow_mixed_currencies)
    return PriceData(prices, metadata, _limitations(metadata, allow_mixed_currencies))


def load_price_panel(
    data_dir: Path = Path("data"),
    *,
    instruments: list[str] | tuple[str, ...] | None = None,
    allow_mixed_currencies: bool = False,
) -> pd.DataFrame:
    """Load only the wide close-price panel from a configurable directory.

    :param data_dir: Directory containing source CSV files.
    :param instruments: Optional exact filename stems to include.
    :param allow_mixed_currencies: Explicitly permit known currency mismatches.
    :return: Wide close-price panel with one column per selected file.
    """
    return load_price_data(
        data_dir,
        instruments=instruments,
        allow_mixed_currencies=allow_mixed_currencies,
    ).prices
