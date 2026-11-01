"""Tests for the downloader orchestration."""

from datetime import date
from pathlib import Path

import pytest

from portfolio_utils.download.downloader import download_etfs
from portfolio_utils.download.errors import (
    InstrumentNotFoundError,
    NoHistoryError,
    UnexpectedResponseError,
)
from portfolio_utils.download.models import Instrument, PriceRow


class FakeSource:
    """In-memory source for download orchestration tests."""

    def __init__(self, instruments: list[Instrument]) -> None:
        self.instruments = instruments
        self.history_calls: list[tuple[str, date | None, date | None]] = []

    def list_etfs(self) -> list[Instrument]:
        """Return configured instruments."""
        return self.instruments

    def resolve(self, identifier: str) -> Instrument:
        """Resolve a test identifier."""
        for item in self.instruments:
            if item.symbol == identifier:
                return item
        raise InstrumentNotFoundError(f"No ETF matching {identifier!r}.")

    def history(
        self,
        instrument: Instrument,
        start: date | None,
        end: date | None,
    ) -> list[PriceRow]:
        """Return a deterministic history."""
        self.history_calls.append((instrument.symbol, start, end))
        return [
            PriceRow(date(2024, 1, 2), 10.0, 12.0, 9.0, 11.0, 100),
            PriceRow(date(2024, 1, 3), 11.0, 13.0, 10.0, 12.0, 101),
        ]


def instrument(symbol: str = "FUND") -> Instrument:
    """Create a sample ETF descriptor."""
    return Instrument(
        investing_id="id-1",
        name="Sample ETF",
        isin="XX0000000000",
        symbol=symbol,
        exchange="Example exchange",
        currency="EUR",
    )


def test_downloader_uses_catalog_and_defaults_to_available_date_range(
    tmp_path: Path,
) -> None:
    """Omitted identifiers and dates use catalog and returned history."""
    source = FakeSource([instrument()])

    paths = download_etfs(
        source=source,
        output_dir=tmp_path,
    )

    assert paths == [tmp_path / "Sample_ETF_20240102_20240103.csv"]
    assert source.history_calls == [("FUND", None, None)]
    assert (
        paths[0]
        .read_text(encoding="utf-8")
        .startswith("date,open,high,low,close,volume\n")
    )


def test_downloader_filters_requested_dates(tmp_path: Path) -> None:
    """Explicit date bounds are passed through and enforced."""
    source = FakeSource([instrument()])

    paths = download_etfs(
        identifiers=["FUND"],
        start=date(2024, 1, 3),
        end=date(2024, 1, 3),
        source=source,
        output_dir=tmp_path,
    )

    assert source.history_calls == [("FUND", date(2024, 1, 3), date(2024, 1, 3))]
    assert paths[0].name == "Sample_ETF_20240103_20240103.csv"


def test_downloader_rejects_empty_catalog_and_history(tmp_path: Path) -> None:
    """Empty results cannot be mistaken for successful downloads."""
    with pytest.raises(UnexpectedResponseError, match="catalog"):
        download_etfs(source=FakeSource([]), output_dir=tmp_path)

    class EmptyHistory(FakeSource):
        def history(
            self,
            instrument: Instrument,
            start: date | None,
            end: date | None,
        ) -> list[PriceRow]:
            _ = instrument, start, end
            return []

    with pytest.raises(UnexpectedResponseError, match="Historical response"):
        download_etfs(
            identifiers=["FUND"],
            source=EmptyHistory([instrument()]),
            output_dir=tmp_path,
        )


def test_catalog_download_skips_etfs_without_history(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The all-ETF run continues past listed instruments without price history."""

    class MixedHistory(FakeSource):
        def history(
            self,
            instrument: Instrument,
            start: date | None,
            end: date | None,
        ) -> list[PriceRow]:
            if instrument.symbol == "EMPTY":
                return []
            return super().history(instrument, start, end)

    source = MixedHistory(
        [
            instrument("EMPTY"),
            Instrument("id-2", "Available ETF", "", "AVAILABLE", "", ""),
        ]
    )

    paths = download_etfs(source=source, output_dir=tmp_path)

    assert [path.name for path in paths] == ["Available_ETF_20240102_20240103.csv"]
    assert "Skipping ETF without available history: Sample ETF" in caplog.text


def test_explicit_download_reports_missing_history(tmp_path: Path) -> None:
    """A requested ETF with no history is an explicit error."""

    class EmptyHistory(FakeSource):
        def history(
            self,
            instrument: Instrument,
            start: date | None,
            end: date | None,
        ) -> list[PriceRow]:
            _ = instrument, start, end
            return []

    with pytest.raises(NoHistoryError, match="no price rows"):
        download_etfs(
            identifiers=["FUND"],
            source=EmptyHistory([instrument()]),
            output_dir=tmp_path,
        )


def test_unknown_identifier_has_explicit_not_found_error(tmp_path: Path) -> None:
    """Unknown identifiers do not silently produce empty downloads."""
    with pytest.raises(InstrumentNotFoundError, match="NOT-A-FUND"):
        download_etfs(
            identifiers=["NOT-A-FUND"],
            source=FakeSource([instrument()]),
            output_dir=tmp_path,
        )


def test_downloader_rejects_reversed_range_and_incomplete_instrument(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="on or before"):
        download_etfs(
            identifiers=["FUND"],
            start=date(2024, 1, 3),
            end=date(2024, 1, 2),
            source=FakeSource([instrument()]),
            output_dir=tmp_path,
        )

    incomplete = Instrument("", "Missing ID", "", "FUND", "", "")
    with pytest.raises(UnexpectedResponseError, match="metadata is incomplete"):
        download_etfs(
            source=FakeSource([incomplete]),
            output_dir=tmp_path,
        )


def test_downloader_rejects_history_outside_requested_range(
    tmp_path: Path,
) -> None:
    with pytest.raises(UnexpectedResponseError, match="no rows in the date range"):
        download_etfs(
            identifiers=["FUND"],
            start=date(2025, 1, 1),
            source=FakeSource([instrument()]),
            output_dir=tmp_path,
        )


def test_downloader_sanitizes_international_instrument_names(
    tmp_path: Path,
) -> None:
    class InternationalSource(FakeSource):
        def list_etfs(self) -> list[Instrument]:
            return [Instrument("id-1", "Café / 株式", "", "FUND", "", "EUR")]

    paths = download_etfs(
        source=InternationalSource([]),
        output_dir=tmp_path,
    )

    assert paths[0].name == "Cafe_20240102_20240103.csv"


def test_downloader_rejects_instrument_name_without_safe_characters(
    tmp_path: Path,
) -> None:
    class UnnamedSource(FakeSource):
        def list_etfs(self) -> list[Instrument]:
            return [Instrument("id-1", "株式", "", "FUND", "", "")]

    with pytest.raises(UnexpectedResponseError, match="safe filename"):
        download_etfs(source=UnnamedSource([]), output_dir=tmp_path)
