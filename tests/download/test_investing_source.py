"""Offline tests for the verified public Investing.com adapter."""

import json
from collections.abc import Mapping
from datetime import date, timedelta
from pathlib import Path

import pytest

from portfolio_utils.download.errors import (
    InstrumentNotFoundError,
    NoHistoryError,
    UnexpectedResponseError,
)
from portfolio_utils.download.models import Instrument
from portfolio_utils.download.source import (
    HISTORY_CAP,
    InvestingComSource,
)

RESOURCES = Path(__file__).parents[1] / "resources" / "investing"


class FakeResponse:
    """Recorded HTTP response used by all source tests."""

    def __init__(self, payload: object, text: str = "") -> None:
        self.status_code = 200
        self.payload = payload
        self.text = text

    def json(self) -> object:
        """Return recorded JSON."""
        return self.payload


class FakeSession:
    """Sequential fake session recording URLs and parameters."""

    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[
            tuple[str, Mapping[str, str] | None, Mapping[str, str] | None]
        ] = []

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, str] | None,
        headers: Mapping[str, str] | None,
        timeout: float,
    ) -> FakeResponse:
        """Return a recorded response without using the network."""
        _ = timeout
        self.calls.append((url, params, headers))
        return self.responses.pop(0)


def _read_text(name: str) -> str:
    return (RESOURCES / name).read_text(encoding="utf-8")


def _source(session: FakeSession) -> InvestingComSource:
    now = [0.0]

    def sleep(seconds: float) -> None:
        now[0] += seconds

    return InvestingComSource(
        session=session,
        sleep=sleep,
        clock=lambda: now[0],
        today=lambda: date(2026, 10, 31),
    )


def test_catalog_enumerates_index_categories_and_parses_instrument() -> None:
    """Public category rows yield identifier, name and ticker."""
    session = FakeSession(
        [
            FakeResponse({}, _read_text("etf_index_ok.html")),
            FakeResponse({}, _read_text("etf_category_row_ok.html")),
        ]
    )

    instruments = _source(session).list_etfs()

    assert instruments == [Instrument("123", "Example ETF", "", "XYZ", "", "")]
    assert session.calls[0][0] == "https://www.investing.com/etfs/"
    assert session.calls[1][0] == "https://www.investing.com/etfs/usa-etfs"


def test_resolve_matches_symbol_from_category_listing() -> None:
    """Ticker lookup scans the public root-linked catalog."""
    session = FakeSession(
        [
            FakeResponse({}, _read_text("etf_index_ok.html")),
            FakeResponse({}, _read_text("etf_category_row_ok.html")),
        ]
    )

    assert _source(session).resolve("xyz").investing_id == "123"


def test_resolve_raises_for_missing_symbol() -> None:
    """A missing ticker has a deliberate not-found outcome."""
    session = FakeSession(
        [
            FakeResponse({}, _read_text("etf_index_ok.html")),
            FakeResponse({}, _read_text("etf_category_row_ok.html")),
        ]
    )

    with pytest.raises(InstrumentNotFoundError, match="ABSENT"):
        _source(session).resolve("ABSENT")


def test_history_parses_fixture_and_uses_verified_parameters() -> None:
    """Historical rows map raw endpoint fields to the documented OHLCV shape."""
    payload = json.loads(_read_text("historical_daily_ok.json"))
    session = FakeSession([FakeResponse(payload)])
    instrument = Instrument("525", "Example ETF", "", "XYZ", "", "")

    rows = _source(session).history(instrument, date(2024, 1, 1), date(2024, 1, 5))

    assert len(rows) == 1
    assert rows[0].date == date(2024, 1, 4)
    assert rows[0].open == pytest.approx(468.29998779296875)
    assert rows[0].volume == 84232168
    url, params, headers = session.calls[0]
    assert url.endswith("/historical/525")
    assert params == {
        "time-frame": "Daily",
        "add-missing-rows": "false",
        "start-date": "2024-01-01",
        "end-date": "2024-01-05",
    }
    assert headers == {"domain-id": "www"}


def test_history_expands_ohlc_bounds_to_include_reported_open_and_close(
    caplog: pytest.LogCaptureFixture,
) -> None:
    record = {
        "rowDateTimestamp": "2025-12-25T00:00:00Z",
        "last_openRaw": "3.4",
        "last_maxRaw": "3.35",
        "last_minRaw": "3.35",
        "last_closeRaw": "3.35",
        "volumeRaw": 0,
    }

    rows = _source(FakeSession([FakeResponse({"data": [record]})])).history(
        Instrument("525", "Example ETF", "", "XYZ", "", ""),
        date(2025, 12, 25),
        date(2025, 12, 25),
    )

    assert rows[0].high == pytest.approx(3.4)
    assert rows[0].low == pytest.approx(3.35)
    assert "corrected high/low to include open and close" in caplog.text


def test_history_continues_after_observed_4999_row_cap() -> None:
    """A capped oldest chunk is followed from latest-returned-date plus one day."""
    first_date = date(1950, 1, 1)
    dates = [first_date + timedelta(days=index) for index in range(HISTORY_CAP)]
    raw_rows = [
        {
            "rowDateTimestamp": f"{day.isoformat()}T00:00:00Z",
            "last_openRaw": "10",
            "last_maxRaw": "12",
            "last_minRaw": "9",
            "last_closeRaw": "11",
            "volumeRaw": 100,
        }
        for day in reversed(dates)
    ]
    next_day = dates[-1] + timedelta(days=1)
    continuation = {
        "data": [
            {
                "rowDateTimestamp": f"{next_day.isoformat()}T00:00:00Z",
                "last_openRaw": "10",
                "last_maxRaw": "12",
                "last_minRaw": "9",
                "last_closeRaw": "11",
                "volumeRaw": 101,
            }
        ],
        "summary": {},
    }
    session = FakeSession(
        [FakeResponse({"data": raw_rows}), FakeResponse(continuation)]
    )

    rows = _source(session).history(
        Instrument("525", "Example ETF", "", "XYZ", "", ""),
        first_date,
        next_day,
    )

    assert len(rows) == HISTORY_CAP + 1
    assert rows[0].date == first_date
    assert rows[-1].date == next_day
    assert session.calls[1][1] is not None
    assert session.calls[1][1]["start-date"] == next_day.isoformat()


def test_history_rejects_empty_response() -> None:
    """An empty initial history response is never reported as a successful download."""
    session = FakeSession([FakeResponse({"data": [], "summary": {}})])

    with pytest.raises(UnexpectedResponseError, match="no price rows"):
        _source(session).history(
            Instrument("525", "Example ETF", "", "XYZ", "", ""),
            date(2024, 1, 1),
            date(2024, 1, 2),
        )


def test_history_treats_null_data_as_no_history() -> None:
    source = _source(FakeSession([FakeResponse({"data": None, "summary": {}})]))

    with pytest.raises(NoHistoryError, match="no price rows"):
        source.history(
            Instrument("525", "Example ETF", "", "XYZ", "", ""),
            date(2024, 1, 1),
            date(2024, 1, 2),
        )


def test_catalog_follows_pagination_and_deduplicates_instruments() -> None:
    """Category pages may contain pagination links and repeated ETF rows."""
    root = '<a href="/etfs/usa-etfs">USA</a>'
    row = (
        '<tr id="pair_123"><span data-name="Example ETF" data-id="123"></span>'
        '<td class="left symbol" title="XYZ"></td>'
        '<a href="/etfs/example-etf">detail</a></tr>'
    )
    category = f'{row}<a href="/etfs/usa-etfs?page=2">Next</a>'
    session = FakeSession(
        [
            FakeResponse({}, root),
            FakeResponse({}, category),
            FakeResponse({}, row),
        ]
    )

    instruments = _source(session).list_etfs()

    assert [item.symbol for item in instruments] == ["XYZ"]
    assert len(session.calls) == 3
    assert session.calls[-1][0].endswith("?page=2")


@pytest.mark.parametrize(
    ("index_html", "category_html", "message"),
    [
        ("<html></html>", "", "no recognizable category"),
        ('<a href="/etfs/usa-etfs">USA</a>', "", "no usable instruments"),
        (
            '<a href="/etfs/usa-etfs">USA</a>',
            '<tr id="pair_123"><span data-name="A" data-id="456"></span>'
            '<td class="left symbol" title="A"></td>'
            '<a href="/etfs/a">detail</a></tr>',
            "did not match",
        ),
    ],
)
def test_catalog_rejects_unusable_pages(
    index_html: str, category_html: str, message: str
) -> None:
    session = FakeSession(
        [FakeResponse({}, index_html), FakeResponse({}, category_html)]
    )

    with pytest.raises(UnexpectedResponseError, match=message):
        _source(session).list_etfs()


def test_history_uses_default_dates_and_stops_after_empty_continuation() -> None:
    record = json.loads(_read_text("historical_daily_ok.json"))["data"][0]
    session = FakeSession(
        [
            FakeResponse({"data": [record] * HISTORY_CAP}),
            FakeResponse({"data": []}),
        ]
    )

    rows = _source(session).history(
        Instrument("525", "Example ETF", "", "XYZ", "", ""), None, None
    )

    assert len(rows) == 1
    assert len(session.calls) == 2
    assert session.calls[0][1] is not None
    assert session.calls[0][1]["start-date"] == "1950-01-01"
    assert session.calls[0][1]["end-date"] == "2026-10-31"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "data list"),
        ({}, "data list"),
        ({"data": [None]}, "was not an object"),
        ({"data": [{"rowDateTimestamp": "bad"}]}, "daily OHLCV shape"),
        (
            {
                "data": [
                    {
                        "rowDateTimestamp": "2023-12-31T00:00:00Z",
                        "last_openRaw": "10",
                        "last_maxRaw": "12",
                        "last_minRaw": "9",
                        "last_closeRaw": "11",
                        "volumeRaw": 1,
                    }
                ]
            },
            "outside the requested range",
        ),
    ],
)
def test_history_rejects_malformed_or_out_of_range_payloads(
    payload: object, message: str
) -> None:
    session = FakeSession([FakeResponse(payload)])

    with pytest.raises(UnexpectedResponseError, match=message):
        _source(session).history(
            Instrument("525", "Example ETF", "", "XYZ", "", ""),
            date(2024, 1, 1),
            date(2024, 1, 5),
        )


def test_history_rejects_reversed_range_and_noninteger_volume() -> None:
    source = _source(FakeSession([]))
    with pytest.raises(ValueError, match="on or before"):
        source.history(
            Instrument("525", "Example ETF", "", "XYZ", "", ""),
            date(2024, 1, 2),
            date(2024, 1, 1),
        )

    invalid_row = {
        "rowDateTimestamp": "2024-01-02T00:00:00Z",
        "last_openRaw": "10",
        "last_maxRaw": "12",
        "last_minRaw": "9",
        "last_closeRaw": "11",
        "volumeRaw": "100",
    }
    with pytest.raises(UnexpectedResponseError, match="daily OHLCV shape"):
        _source(FakeSession([FakeResponse({"data": [invalid_row]})])).history(
            Instrument("525", "Example ETF", "", "XYZ", "", ""),
            date(2024, 1, 1),
            date(2024, 1, 5),
        )
