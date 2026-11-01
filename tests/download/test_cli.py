"""Offline tests for the downloader command-line entry point."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pytest

from portfolio_utils.download import cli as download_cli
from portfolio_utils.download.errors import DownloadError
from portfolio_utils.download.models import Instrument, PriceRow
from portfolio_utils.download.source import InvestingDataSource


def test_downloader_cli_forwards_arguments_and_prints_paths(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    destination = tmp_path / "asset.csv"
    captured: dict[str, Sequence[str] | date | Path | InvestingDataSource | None] = {}

    def fake_download(
        identifiers: Sequence[str] | None = None,
        start: date | None = None,
        end: date | None = None,
        *,
        output_dir: Path | None = None,
        source: InvestingDataSource | None = None,
    ) -> list[Path]:
        _ = source
        captured.update(
            identifiers=identifiers,
            start=start,
            end=end,
            output_dir=output_dir,
            source=source,
        )
        return [destination]

    monkeypatch.setattr(download_cli, "download_etfs", fake_download)

    status = download_cli.main(
        [
            "ETF",
            "--start",
            "2024-01-01",
            "--end",
            "2024-01-31",
            "--output",
            str(tmp_path),
        ]
    )

    assert status == 0
    assert captured["identifiers"] == ["ETF"]
    assert captured["start"] == date(2024, 1, 1)
    assert captured["end"] == date(2024, 1, 31)
    assert captured["output_dir"] == tmp_path
    assert captured["source"] is None
    assert capsys.readouterr().out == f"{destination}\n"


def test_downloader_cli_resume_filters_existing_catalog_files(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    existing = Instrument("1", "Sample ETF", "", "", "", "")
    pending = Instrument("2", "Pending ETF", "", "", "", "")

    class FakeCatalog:
        def list_etfs(self) -> list[Instrument]:
            return [existing, pending]

        def resolve(self, identifier: str) -> Instrument:
            raise AssertionError(identifier)

        def history(
            self,
            instrument: Instrument,
            start: date | None,
            end: date | None,
        ) -> list[PriceRow]:
            raise AssertionError((instrument, start, end))

    monkeypatch.setattr(download_cli, "InvestingComSource", FakeCatalog)
    captured_source: InvestingDataSource | None = None

    def fake_download(
        identifiers: Sequence[str] | None = None,
        start: date | None = None,
        end: date | None = None,
        *,
        output_dir: Path | None = None,
        source: InvestingDataSource | None = None,
    ) -> list[Path]:
        nonlocal captured_source
        _ = identifiers, start, end, output_dir
        captured_source = source
        return []

    monkeypatch.setattr(download_cli, "download_etfs", fake_download)
    (tmp_path / "Sample_ETF_20240102_20240103.csv").touch()

    status = download_cli.main(["--resume", "--output", str(tmp_path)])

    assert status == 0
    assert captured_source is not None
    assert [item.name for item in captured_source.list_etfs()] == ["Pending ETF"]
    assert "skipping 1 ETFs" in capsys.readouterr().err


def test_downloader_cli_reports_download_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail_download(*_args: object, **_kwargs: object) -> list[Path]:
        raise DownloadError("offline test failure")

    monkeypatch.setattr(download_cli, "download_etfs", fail_download)

    with pytest.raises(SystemExit) as result:
        download_cli.main(["ETF"])

    assert result.value.code == 2
    assert capsys.readouterr().err == "download failed: offline test failure\n"


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--start", "2024-02-01", "--end", "2024-01-01"], "on or before"),
        (["--start", "not-a-date"], "ISO date"),
    ],
)
def test_downloader_cli_rejects_invalid_dates(
    monkeypatch: pytest.MonkeyPatch,
    arguments: list[str],
    message: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def unexpected_download(*_args: object, **_kwargs: object) -> list[Path]:
        pytest.fail("download must not run for invalid command-line arguments")

    monkeypatch.setattr(download_cli, "download_etfs", unexpected_download)

    with pytest.raises(SystemExit) as result:
        download_cli.main(arguments)

    assert result.value.code == 2
    assert message in capsys.readouterr().err
