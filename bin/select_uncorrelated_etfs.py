#!/usr/bin/env python3
"""Select a deterministic subset of instruments by return correlation."""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from portfolio_utils.analysis import (  # noqa: E402
    align_prices,
    load_price_panel,
    prices_to_returns,
)

_MIN_PRICE_OBSERVATIONS = 3


def _date(value: str) -> pd.Timestamp:
    """Parse a timezone-naive CLI date.

    :param value: ISO-formatted date.
    :raises argparse.ArgumentTypeError: If the value is not a valid date.
    :return: Parsed calendar date.
    """
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError("Use a valid YYYY-MM-DD date.") from error
    if pd.isna(parsed) or parsed.tz is not None:
        raise argparse.ArgumentTypeError("Use a timezone-naive YYYY-MM-DD date.")
    return parsed.normalize()


def _parser() -> argparse.ArgumentParser:
    """Create the correlation-selection command parser.

    :return: Configured argument parser.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Select a deterministic subset whose pairwise absolute linear "
            "correlations of simple returns are strictly below the threshold."
        )
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument(
        "--instruments",
        nargs="+",
        help="Optional CSV filenames or stems; defaults to every CSV in the directory.",
    )
    parser.add_argument("--start-date", type=_date)
    parser.add_argument("--end-date", type=_date)
    parser.add_argument(
        "--max-abs-correlation",
        type=float,
        default=0.4,
        help="Strict maximum absolute simple-return correlation (default: 0.4).",
    )
    return parser


def _select_names(correlation: pd.DataFrame, threshold: float) -> list[str]:
    """Greedily retain lexically ordered names meeting strict pair limits.

    :param correlation: Correlation matrix of complete return series.
    :param threshold: Maximum permitted absolute pairwise correlation.
    :return: Deterministic selected instrument names.
    """
    selected: list[str] = []
    for instrument in sorted(str(name) for name in correlation.columns):
        if all(
            abs(cast(float, correlation.loc[instrument, prior])) < threshold
            for prior in selected
        ):
            selected.append(instrument)
    return selected


def _correlation_report(
    prices: pd.DataFrame,
    start_date: pd.Timestamp | None,
    end_date: pd.Timestamp | None,
    threshold: float,
) -> tuple[list[str], pd.DataFrame, pd.Timestamp, pd.Timestamp]:
    """Calculate selected instruments and their simple-return correlation.

    :param prices: Loaded price panel.
    :param start_date: Optional inclusive first price date.
    :param end_date: Optional inclusive last price date.
    :param threshold: Strict maximum absolute correlation.
    :raises ValueError: If the interval or return data cannot be analyzed.
    :return: Selected names, their correlation matrix, and effective dates.
    """
    aligned = align_prices(prices, policy="inner").sort_index()
    start = start_date or pd.Timestamp(aligned.index[0])
    end = end_date or pd.Timestamp(aligned.index[-1])
    if start > end:
        raise ValueError("start-date must not be later than end-date.")
    window = aligned.loc[(aligned.index >= start) & (aligned.index <= end)]
    if len(window) < _MIN_PRICE_OBSERVATIONS:
        raise ValueError("At least three common prices are needed for correlation.")
    returns = prices_to_returns(window, method="simple", alignment_policy="inner")
    correlation = returns.corr()
    if not math.isfinite(float(correlation.to_numpy(dtype=float).min())) or (
        not math.isfinite(float(correlation.to_numpy(dtype=float).max()))
    ):
        raise ValueError(
            "Return correlation is undefined; check for constant instrument returns."
        )
    names = _select_names(correlation, threshold)
    return (
        names,
        correlation.loc[names, names],
        pd.Timestamp(window.index[0]),
        pd.Timestamp(window.index[-1]),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the correlation-selection command.

    :param argv: Optional command-line arguments, excluding the program name.
    :raises SystemExit: If command-line arguments or input data are invalid.
    :return: Successful process status.
    """
    parser = _parser()
    args = parser.parse_args(argv)
    if not math.isfinite(args.max_abs_correlation) or not (
        0.0 <= args.max_abs_correlation <= 1.0
    ):
        parser.error("--max-abs-correlation must be between 0 and 1.")
    try:
        prices = load_price_panel(
            args.data_dir,
            instruments=(
                sorted(Path(filename).stem for filename in args.instruments)
                if args.instruments is not None
                else None
            ),
        )
        names, matrix, start, end = _correlation_report(
            prices, args.start_date, args.end_date, args.max_abs_correlation
        )
    except (FileNotFoundError, ValueError) as error:
        parser.error(str(error))
    lines = (
        "Correlation selection uses simple-return correlations.",
        f"Common price period: {start.date()} to {end.date()}",
        f"Strict maximum absolute correlation: {args.max_abs_correlation:g}",
        f"Selected instruments ({len(names)}): {', '.join(names) or '(none)'}",
        "Correlation matrix for selected simple-return series:",
        matrix.to_string(float_format=lambda value: f"{value:.6f}"),
    )
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
