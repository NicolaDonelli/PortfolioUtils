"""Verified public Investing.com ETF pages and historical-data endpoint.

Verification date: 2026-10-31, using public ``curl_cffi`` GET requests only. No
account, login flow, cookies, or protection bypass is used. Site pages returned 200
with a Chrome-impersonating ``curl_cffi`` session; direct Playwright navigation to a
detail page returned 403.

Undocumented endpoints observed and used by :class:`InvestingComSource`:

* ETF index: ``GET https://www.investing.com/etfs/``; no query parameters and no
  application-supplied headers (``curl_cffi`` Chrome impersonation defaults).
  Response is HTML with links to category pages.
* Category pages: ``GET https://www.investing.com/etfs/{category}``, where the index
  exposed ``usa-etfs``, ``world-etfs``, ``major-etfs``, and ``cannabis-etfs``; no
  query parameters and no application-supplied headers. HTML rows contain
  ``tr#pair_<id>``, a ``span[data-name][data-id]``, a symbol cell
  ``td.left.symbol[title]``, and an ETF detail link. At verification, responses had
  1000 USA rows, 708 World rows, 37 Major rows, and 12 Cannabis rows. No pagination
  links were found in these observed HTML pages. The category set and contents may
  change; enumeration is limited to root-linked categories and explicit pagination
  links and is not claimed to be an exhaustive Investing.com catalog.
* ETF detail pages: ``GET https://www.investing.com/etfs/{slug}``; no query
  parameters and no application-supplied headers. The observed Next.js payload
  included ``props.pageProps.identifiers.instrument_id`` and ``type="etf"``.
  Category-row identifiers are used directly; detail pages are not fetched per ETF.
* Historical prices: ``GET
  https://api.investing.com/api/financialdata/historical/{instrument_id}`` with
  ``start-date=YYYY-MM-DD``, ``end-date=YYYY-MM-DD``, ``time-frame=Daily``, and
  ``add-missing-rows=false``; required application header ``domain-id: www``.
  Response is JSON with ``data`` and ``summary``; daily data uses
  ``rowDateTimestamp``, ``last_openRaw``, ``last_maxRaw``, ``last_minRaw``,
  ``last_closeRaw``, and ``volumeRaw``. Rows are descending. A wide SPY request
  returned 4999 earliest records; the adapter advances from the latest returned
  date plus one day to retrieve subsequent records.

Fixtures in ``tests/resources/investing/`` contain small anonymized examples. There
is no general search endpoint: identifier lookup scans the observed root-linked
category tables, so an identifier outside those categories can remain unresolved.
"""

import logging
import re
import time
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from html.parser import HTMLParser
from typing import Protocol, cast
from urllib.parse import urljoin, urlsplit

from curl_cffi import requests

from portfolio_utils.download.client import HttpSession, InvestingHttpClient
from portfolio_utils.download.errors import (
    InstrumentNotFoundError,
    NoHistoryError,
    UnexpectedResponseError,
)
from portfolio_utils.download.models import Instrument, PriceRow
from portfolio_utils.download.storage import merge_rows

SITE_ROOT = "https://www.investing.com"
ETF_INDEX_URL = f"{SITE_ROOT}/etfs/"
HISTORY_URL = "https://api.investing.com/api/financialdata/historical/{instrument_id}"
HISTORY_HEADERS = {"domain-id": "www"}
HISTORY_PARAMS = {
    "time-frame": "Daily",
    "add-missing-rows": "false",
}
HISTORY_CAP = 4999
DEFAULT_HISTORY_START = date(1950, 1, 1)
CATEGORY_PATH = re.compile(r"^/etfs/[a-z0-9-]+-etfs/?$")
PAGINATION_PATH = re.compile(r"(?:[?&](?:page|offset)=|/page/\d+)", re.IGNORECASE)
LOGGER = logging.getLogger(__name__)


class InvestingDataSource(Protocol):
    """Data-provider contract implemented by the public Investing.com adapter."""

    def list_etfs(self) -> Sequence[Instrument]:
        """Return instruments found in root-linked public ETF categories."""
        ...

    def resolve(self, identifier: str) -> Instrument:
        """Resolve a ticker, ISIN, name, or numeric ID against public categories."""
        ...

    def history(
        self,
        instrument: Instrument,
        start: date | None,
        end: date | None,
    ) -> Sequence[PriceRow]:
        """Return daily historical prices from the public endpoint."""
        ...


class _PageParser(HTMLParser):
    """Extract root category links or ETF rows from public HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.category_paths: set[str] = set()
        self.pagination_links: set[str] = set()
        self.instruments: list[Instrument] = []
        self._row: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}
        href = attr.get("href", "")
        self._add_links(tag, href)
        if tag == "tr" and attr.get("id", "").startswith("pair_"):
            self._row = {"row_id": attr["id"].removeprefix("pair_")}
        elif self._row is not None:
            self._set_row_fields(tag, attr, href)

    def _add_links(self, tag: str, href: str) -> None:
        if tag == "a" and href:
            path = urlsplit(href).path
            if CATEGORY_PATH.fullmatch(path):
                self.category_paths.add(path)
            if PAGINATION_PATH.search(href):
                self.pagination_links.add(urljoin(SITE_ROOT, href))

    def _set_row_fields(self, tag: str, attr: dict[str, str], href: str) -> None:
        if self._row is None:
            return
        if attr.get("data-name"):
            self._row["name"] = attr["data-name"]
        if attr.get("data-id"):
            self._row["data_id"] = attr["data-id"]
        if tag == "td" and {"left", "symbol"}.issubset(
            set(attr.get("class", "").split())
        ):
            self._row["symbol"] = attr.get("title", "")
        if tag == "a" and href.startswith("/etfs/"):
            self._row["detail_path"] = urlsplit(href).path

    def handle_endtag(self, tag: str) -> None:
        if tag != "tr" or self._row is None:
            return
        row = self._row
        self._row = None
        instrument_id = row.get("data_id") or row["row_id"]
        if not (row.get("name") and row.get("symbol") and row.get("detail_path")):
            return
        if instrument_id != row["row_id"]:
            raise UnexpectedResponseError(
                "ETF category row ID did not match its instrument data ID."
            )
        self.instruments.append(
            Instrument(
                investing_id=instrument_id,
                name=row["name"],
                isin="",
                symbol=row["symbol"],
                exchange="",
                currency="",
            )
        )


class InvestingComSource:
    """Sequential public ETF catalog and historical-price adapter."""

    def __init__(
        self,
        session: HttpSession | None = None,
        min_interval_s: float = 1.5,
        sleep: Callable[[float], None] | None = None,
        clock: Callable[[], float] | None = None,
        today: Callable[[], date] | None = None,
    ) -> None:
        """Initialize one reusable serial public HTTP session.

        :param session: Optional injected fake or real HTTP session.
        :param min_interval_s: Minimum request-start interval.
        :param sleep: Optional injected sleep function.
        :param clock: Optional injected monotonic clock.
        :param today: Optional injected date provider.
        """
        actual_session = session or cast(
            HttpSession, requests.Session(impersonate="chrome")
        )
        self._client = InvestingHttpClient(
            actual_session,
            min_interval_s=min_interval_s,
            sleep=time.sleep if sleep is None else sleep,
            clock=time.monotonic if clock is None else clock,
        )
        self._today = today or (lambda: datetime.now(UTC).date())

    def list_etfs(self) -> list[Instrument]:
        """Enumerate ETFs from root-linked categories and explicit page links.

        :raises UnexpectedResponseError: If pages contain no usable ETF rows.
        :return: Deduplicated instruments in category discovery order.
        """
        root = _PageParser()
        root.feed(self._client.get_text(ETF_INDEX_URL))
        if not root.category_paths:
            raise UnexpectedResponseError(
                "The ETF index contained no recognizable category links."
            )
        instruments: dict[str, Instrument] = {}
        pending = [urljoin(SITE_ROOT, path) for path in sorted(root.category_paths)]
        visited: set[str] = set()
        while pending:
            page_url = pending.pop(0)
            if page_url in visited:
                continue
            visited.add(page_url)
            parser = _PageParser()
            parser.feed(self._client.get_text(page_url))
            for instrument in parser.instruments:
                instruments.setdefault(instrument.investing_id, instrument)
            pending.extend(
                sorted(parser.pagination_links.difference(visited).difference(pending))
            )
        if not instruments:
            raise UnexpectedResponseError(
                "Root-linked ETF category pages contained no usable instruments."
            )
        return list(instruments.values())

    def resolve(self, identifier: str) -> Instrument:
        """Resolve a ticker, ISIN, name, or numeric ID by scanning public categories.

        :param identifier: ETF symbol, ISIN, name, or Investing.com ID.
        :raises InstrumentNotFoundError: If no root-linked category matches.
        :return: Matching ETF descriptor.
        """
        needle = identifier.strip().casefold()
        for instrument in self.list_etfs():
            candidates = (
                instrument.symbol,
                instrument.isin,
                instrument.name,
                instrument.investing_id,
            )
            if needle in {
                candidate.casefold() for candidate in candidates if candidate
            }:
                return instrument
        raise InstrumentNotFoundError(
            f"No ETF matching {identifier!r} was found in root-linked categories."
        )

    def history(
        self,
        instrument: Instrument,
        start: date | None,
        end: date | None,
    ) -> list[PriceRow]:
        """Fetch all available daily rows, continuing after the observed 4999 cap.

        :param instrument: Resolved ETF.
        :param start: Inclusive first date; defaults to 1950-01-01.
        :param end: Inclusive final date; defaults to today's UTC date.
        :raises ValueError: If the date range is reversed.
        :return: Validated rows in ascending date order.
        """
        range_start = DEFAULT_HISTORY_START if start is None else start
        range_end = self._today() if end is None else end
        if range_start > range_end:
            raise ValueError("start must be on or before end.")
        cursor = range_start
        collected: list[PriceRow] = []
        while cursor <= range_end:
            next_cursor = self._append_history_page(
                instrument, cursor, range_end, collected
            )
            if next_cursor is None:
                break
            cursor = next_cursor
        return merge_rows([], collected)

    def _append_history_page(
        self,
        instrument: Instrument,
        cursor: date,
        range_end: date,
        collected: list[PriceRow],
    ) -> date | None:
        params = {
            **HISTORY_PARAMS,
            "start-date": cursor.isoformat(),
            "end-date": range_end.isoformat(),
        }
        payload = self._client.get_json(
            HISTORY_URL.format(instrument_id=instrument.investing_id),
            params=params,
            headers=HISTORY_HEADERS,
        )
        records = _history_records(payload, has_collected=bool(collected))
        if records is None:
            return None
        if not records:
            if collected:
                return None
            raise NoHistoryError("Historical response contained no price rows.")
        chunk = [_parse_history_row(record) for record in records]
        if any(row.date < cursor or row.date > range_end for row in chunk):
            raise UnexpectedResponseError(
                "Historical response contained a row outside the requested range."
            )
        collected.extend(chunk)
        if len(records) < HISTORY_CAP:
            return None
        next_start = max(row.date for row in chunk) + timedelta(days=1)
        if next_start <= cursor:
            raise UnexpectedResponseError(
                "Historical cap continuation did not advance the start date."
            )
        return next_start


def _history_records(payload: object, *, has_collected: bool) -> list[object] | None:
    if not isinstance(payload, dict):
        raise UnexpectedResponseError(
            "Historical JSON response must contain a data list."
        )
    if "data" not in payload:
        raise UnexpectedResponseError(
            "Historical JSON response must contain a data list."
        )
    records = payload.get("data")
    if records is None:
        if has_collected:
            return None
        raise NoHistoryError("Historical response contained no price rows.")
    if not isinstance(records, list):
        raise UnexpectedResponseError(
            "Historical JSON response must contain a data list."
        )
    return records


def _parse_history_row(record: object) -> PriceRow:
    if not isinstance(record, dict):
        raise UnexpectedResponseError("Historical row was not an object.")
    try:
        timestamp = record["rowDateTimestamp"]
        if not isinstance(timestamp, str):
            raise ValueError
        row_date = date.fromisoformat(timestamp.replace("Z", "+00:00")[:10])
        open_price = float(record["last_openRaw"])
        high = float(record["last_maxRaw"])
        low = float(record["last_minRaw"])
        close = float(record["last_closeRaw"])
        corrected_high = max(high, open_price, close)
        corrected_low = min(low, open_price, close)
        if corrected_high != high or corrected_low != low:
            LOGGER.warning(
                "Investing.com reported inconsistent OHLC bounds for %s; "
                "corrected high/low to include open and close.",
                row_date,
            )
            high = corrected_high
            low = corrected_low
        raw_volume = record.get("volumeRaw")
        if raw_volume is not None and (
            not isinstance(raw_volume, int) or isinstance(raw_volume, bool)
        ):
            raise ValueError
        return PriceRow(row_date, open_price, high, low, close, raw_volume)
    except (KeyError, TypeError, ValueError):
        raise UnexpectedResponseError(
            "Historical row did not match the observed daily OHLCV shape."
        ) from None
