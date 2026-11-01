"""Command-line entry point for ETF history downloads."""

import argparse
import re
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from portfolio_utils.download import DownloadError, download_etfs
from portfolio_utils.download.downloader import _safe_name
from portfolio_utils.download.models import Instrument, PriceRow
from portfolio_utils.download.source import InvestingComSource, InvestingDataSource

_DATE_RANGE_FILENAME = re.compile(r"(?P<name>.+)_\d{8}_\d{8}\.csv")


class _ResumeCatalogSource:
    """Limit a catalog source to instruments without an existing CSV."""

    def __init__(self, source: InvestingDataSource, output_dir: Path) -> None:
        self._source = source
        existing_names = {
            match.group("name")
            for path in output_dir.glob("*.csv")
            if (match := _DATE_RANGE_FILENAME.fullmatch(path.name)) is not None
        }
        catalog = list(source.list_etfs())
        self._instruments = [
            item for item in catalog if _safe_name(item.name) not in existing_names
        ]
        self.skipped_count = len(catalog) - len(self._instruments)

    def list_etfs(self) -> Sequence[Instrument]:
        """Return only catalog entries not represented by existing CSVs."""
        return self._instruments

    def resolve(self, identifier: str) -> Instrument:
        """Delegate explicit identifier resolution."""
        return self._source.resolve(identifier)

    def history(
        self, instrument: Instrument, start: date | None, end: date | None
    ) -> Sequence[PriceRow]:
        """Delegate history requests to the throttled source."""
        return self._source.history(instrument, start, end)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "Use an ISO date in YYYY-MM-DD format."
        ) from None


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line downloader.

    :param argv: Optional command-line argument sequence for tests.
    :return: Process exit status.
    """
    parser = argparse.ArgumentParser(
        description="Download Investing.com ETF daily history to schema-compatible CSV."
    )
    parser.add_argument(
        "identifiers",
        nargs="*",
        help="ETF ISIN or ticker; omit to enumerate the public ETF catalog.",
    )
    parser.add_argument(
        "--start", type=_parse_date, help="Inclusive date (YYYY-MM-DD)."
    )
    parser.add_argument("--end", type=_parse_date, help="Inclusive date (YYYY-MM-DD).")
    parser.add_argument(
        "--output",
        type=Path,
        help="Output directory (default: data/YYYYMMDD).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="For catalog downloads, skip instruments with date-range CSVs already present.",
    )
    args = parser.parse_args(argv)
    if args.resume and args.identifiers:
        parser.error("--resume is only available when downloading the public catalog.")
    if args.start is not None and args.end is not None and args.start > args.end:
        parser.error("--start must be on or before --end.")
    source: InvestingDataSource | None = None
    if args.resume:
        output_dir = args.output or (
            Path("data") / datetime.now(UTC).date().strftime("%Y%m%d")
        )
        source = _ResumeCatalogSource(InvestingComSource(), output_dir)
        if not source.list_etfs():
            sys.stdout.write("No remaining catalog ETFs to download.\n")
            return 0
        sys.stderr.write(
            f"Resuming catalog download; skipping {source.skipped_count} ETFs "
            "with existing CSVs.\n"
        )
    try:
        paths = download_etfs(
            identifiers=args.identifiers,
            start=args.start,
            end=args.end,
            output_dir=args.output,
            source=source,
        )
    except DownloadError as error:
        parser.exit(2, f"download failed: {error}\n")
    for path in paths:
        sys.stdout.write(f"{path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
