"""ETF history orchestration independent of Investing.com endpoint details."""

import logging
import re
import unicodedata
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from portfolio_utils.download.errors import NoHistoryError, UnexpectedResponseError
from portfolio_utils.download.models import Instrument, PriceRow
from portfolio_utils.download.source import InvestingComSource, InvestingDataSource
from portfolio_utils.download.storage import merge_rows, write_rows

LOGGER = logging.getLogger(__name__)


def _safe_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", normalized).strip("._-")
    if not safe:
        raise UnexpectedResponseError("Instrument name cannot form a safe filename.")
    return safe


def _select_range(
    rows: Sequence[PriceRow], start: date | None, end: date | None
) -> list[PriceRow]:
    if not rows:
        raise NoHistoryError("Historical response contained no price rows.")
    ordered = merge_rows([], list(rows))
    selected = [
        row
        for row in ordered
        if (start is None or row.date >= start) and (end is None or row.date <= end)
    ]
    if not selected:
        raise UnexpectedResponseError(
            "Historical response has no rows in the date range."
        )
    return selected


def _history_rows(
    provider: InvestingDataSource,
    instrument: Instrument,
    start: date | None,
    end: date | None,
    skip_no_history: bool,
) -> list[PriceRow] | None:
    """Fetch and validate one instrument's requested daily history.

    :param provider: Public or injected data provider.
    :param instrument: Instrument supplied by the catalog or resolver.
    :param start: Optional inclusive first date.
    :param end: Optional inclusive final date.
    :param skip_no_history: Whether an instrument without history is skipped.
    :raises NoHistoryError: If history is absent and skipping is disabled.
    :return: Validated rows, or ``None`` for an ETF without history.
    """
    try:
        history = provider.history(instrument, start, end)
        return _select_range(history, start, end)
    except NoHistoryError:
        if not skip_no_history:
            raise
        LOGGER.warning(
            "Skipping ETF without available history: %s",
            instrument.name,
        )
        return None


def download_etfs(
    identifiers: Sequence[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    *,
    output_dir: Path | None = None,
    source: InvestingDataSource | None = None,
) -> list[Path]:
    """Download one or more ETFs sequentially and write CSV history files.

    :param identifiers: ISINs/tickers; omitted identifiers request the public catalog.
    :param start: Inclusive first date; ``None`` means first available observation.
    :param end: Inclusive final date; ``None`` means latest available observation.
    :param output_dir: Output directory; defaults to ``data/YYYYMMDD``.
    :param source: Injectable provider; defaults to the public Investing.com adapter.
    :raises UnexpectedResponseError: If the catalog or returned history is empty/invalid.
    :raises ValueError: If the date range is reversed.
    :return: Paths to the written CSV files in request order.
    """
    if start is not None and end is not None and start > end:
        raise ValueError("start must be on or before end.")
    provider = InvestingComSource() if source is None else source
    catalog_run = not identifiers
    if identifiers:
        instruments = [provider.resolve(identifier) for identifier in identifiers]
    else:
        instruments = list(provider.list_etfs())
        if not instruments:
            raise UnexpectedResponseError(
                "The public ETF catalog returned no instruments."
            )
    run_date = datetime.now(UTC).date()
    destination = output_dir or Path("data") / run_date.strftime("%Y%m%d")
    written: list[Path] = []
    for instrument in instruments:
        if not instrument.investing_id or not instrument.name:
            raise UnexpectedResponseError("Resolved ETF metadata is incomplete.")
        rows = _history_rows(
            provider,
            instrument,
            start,
            end,
            catalog_run,
        )
        if rows is None:
            continue
        filename = (
            f"{_safe_name(instrument.name)}_"
            f"{rows[0].date:%Y%m%d}_{rows[-1].date:%Y%m%d}.csv"
        )
        destination_path = destination / filename
        write_rows(destination_path, rows)
        written.append(destination_path)
    return written
