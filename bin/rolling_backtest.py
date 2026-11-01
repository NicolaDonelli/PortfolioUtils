#!/usr/bin/env python3
"""Run a rolling validation and strictly forward out-of-sample portfolio test."""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from portfolio_utils.analysis import (  # noqa: E402
    BlackLittermanInputs,
    OptimizationConfig,
    OptimizationResult,
    align_prices,
    efficient_cvar,
    efficient_return,
    efficient_risk,
    efficient_semivariance,
    load_price_panel,
    max_quadratic_utility,
    max_sharpe,
    min_cvar,
    min_semivariance,
    min_volatility,
    optimize_black_litterman,
    optimize_hrp,
    prices_to_returns,
)
from portfolio_utils.analysis.metrics import (  # noqa: E402
    annualized_realized_volatility,
    annualized_return,
    annualized_sharpe_ratio,
    annualized_sortino_ratio,
    cumulative_return,
    realized_volatility,
    sharpe_ratio,
    sortino_ratio,
)

METRIC_NAMES = (
    "cumulative_return",
    "annualized_return",
    "realized_volatility",
    "annualized_realized_volatility",
    "sharpe_ratio",
    "annualized_sharpe_ratio",
    "sortino_ratio",
    "annualized_sortino_ratio",
)
_MIN_TRAINING_OBSERVATIONS = 2
Optimizer = Callable[[pd.DataFrame], OptimizationResult]


@dataclass(frozen=True)
class _ValidationWindow:
    """A disjoint validation segment and its strictly prior training returns."""

    start: pd.Timestamp
    end: pd.Timestamp
    training: pd.DataFrame
    validation: pd.DataFrame


def _date(value: str) -> pd.Timestamp:
    """Parse a timezone-naive CLI date.

    :param value: ISO-formatted date.
    :raises argparse.ArgumentTypeError: If the value is invalid.
    :return: Parsed calendar date.
    """
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError("Use a valid YYYY-MM-DD date.") from error
    if pd.isna(parsed) or parsed.tz is not None:
        raise argparse.ArgumentTypeError("Use a timezone-naive YYYY-MM-DD date.")
    return parsed.normalize()


def _positive_years(value: str) -> int:
    """Parse a positive integer number of years.

    :param value: CLI text to parse.
    :raises argparse.ArgumentTypeError: If the value is not positive.
    :return: Positive number of years.
    """
    try:
        years = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Years must be a positive integer.") from error
    if years < 1:
        raise argparse.ArgumentTypeError("Years must be a positive integer.")
    return years


def _parser() -> argparse.ArgumentParser:
    """Create the rolling-backtest command parser.

    :return: Configured argument parser.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Validate rolling strategies on non-overlapping future windows, "
            "then report a separate out-of-sample period. Every optimizer is "
            "fit only to observations strictly before the period it tests."
        )
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument(
        "--instruments",
        nargs="+",
        help="Optional CSV filenames or stems; defaults to every CSV in the directory.",
    )
    parser.add_argument(
        "--strategy",
        choices=(
            "max_sharpe",
            "min_volatility",
            "max_quadratic_utility",
            "efficient_risk",
            "efficient_return",
            "min_cvar",
            "efficient_cvar",
            "min_semivariance",
            "efficient_semivariance",
            "hrp",
            "black_litterman",
        ),
        default="max_sharpe",
    )
    parser.add_argument("--rolling-start", type=_date)
    parser.add_argument("--rolling-end", type=_date)
    parser.add_argument("--train-years", type=_positive_years, default=3)
    parser.add_argument("--validation-years", type=_positive_years, default=1)
    parser.add_argument("--oos-start", type=_date)
    parser.add_argument("--oos-end", type=_date)
    parser.add_argument(
        "--metrics",
        default=",".join(METRIC_NAMES),
        help=f"Comma-separated report metrics; choices: {', '.join(METRIC_NAMES)}.",
    )
    parser.add_argument("--periods-per-year", type=int, default=252)
    parser.add_argument("--risk-free-rate", type=float, default=0.0)
    position = parser.add_mutually_exclusive_group()
    position.add_argument("--long-only", dest="long_only", action="store_true")
    position.add_argument("--allow-short", dest="long_only", action="store_false")
    parser.set_defaults(long_only=True)
    parser.add_argument("--min-weight", type=float)
    parser.add_argument("--max-weight", type=float, default=1.0)
    parser.add_argument("--risk-aversion", type=float, default=1.0)
    parser.add_argument("--solver")
    parser.add_argument("--target-return", type=float)
    parser.add_argument("--target-volatility", type=float)
    parser.add_argument("--cvar-beta", type=float, default=0.95)
    parser.add_argument("--market-caps")
    parser.add_argument("--prior-returns")
    parser.add_argument("--absolute-views")
    parser.add_argument(
        "--relative-view",
        action="append",
        default=[],
        metavar="ASSET=COEFFICIENT,...:TARGET",
        help="Relative Black-Litterman view; may be supplied more than once.",
    )
    parser.add_argument("--tau", type=float, default=0.05)
    return parser


def _named_values(value: str | None, label: str) -> pd.Series[float] | None:
    """Parse comma-separated ``name=value`` numeric input.

    :param value: User-provided mapping text.
    :param label: Name used in validation errors.
    :raises ValueError: If a name or numeric value is invalid.
    :return: Named floating-point values, or ``None`` if omitted.
    """
    if value is None:
        return None
    records: dict[str, float] = {}
    try:
        for item in value.split(","):
            name, number = item.split("=", maxsplit=1)
            if not name.strip() or name.strip() in records:
                raise ValueError
            records[name.strip()] = float(number)
    except ValueError as error:
        raise ValueError(
            f"{label} must use unique ASSET=NUMBER entries separated by commas."
        ) from error
    if not records or not np.isfinite(np.array(list(records.values()))).all():
        raise ValueError(f"{label} values must be finite and non-empty.")
    return pd.Series(records, dtype=float)


def _relative_views(
    specifications: list[str], assets: pd.Index[str]
) -> tuple[pd.DataFrame, pd.Series[float]]:
    """Parse repeated relative-view specifications into matrix and targets.

    :param specifications: Terms formatted ``ASSET=COEFFICIENT,...:TARGET``.
    :param assets: Selected instrument names in optimizer order.
    :raises ValueError: If a view is malformed or names an unknown asset.
    :return: View matrix and its annual target returns.
    """
    rows: list[dict[str, float]] = []
    targets: list[float] = []
    for specification in specifications:
        row_text, separator, target_text = specification.rpartition(":")
        if not separator:
            raise ValueError("Each --relative-view must include :TARGET.")
        values = _named_values(row_text, "relative-view")
        if values is None:
            raise ValueError("Each --relative-view must include coefficients.")
        unknown = set(values.index).difference(assets)
        if unknown:
            raise ValueError(
                f"Relative views contain unknown assets: {', '.join(sorted(unknown))}."
            )
        try:
            target = float(target_text)
        except ValueError as error:
            raise ValueError("Relative view targets must be finite numbers.") from error
        rows.append({asset: float(values.get(asset, 0.0)) for asset in assets})
        targets.append(target)
    if not np.isfinite(np.array(targets, dtype=float)).all():
        raise ValueError("Relative view targets must be finite.")
    return pd.DataFrame(rows, columns=assets), pd.Series(targets, dtype=float)


def _black_litterman_inputs(
    args: argparse.Namespace, assets: pd.Index[str]
) -> BlackLittermanInputs:
    """Parse explicit Black-Litterman priors and views.

    :param args: Parsed command-line arguments.
    :param assets: Selected instrument names in optimizer order.
    :raises ValueError: If required priors or views are missing or invalid.
    :return: Explicit Black-Litterman input object.
    """
    market_caps = _named_values(args.market_caps, "market-caps")
    prior_returns = _named_values(args.prior_returns, "prior-returns")
    absolute_views = _named_values(args.absolute_views, "absolute-views")
    if absolute_views is not None and args.relative_view:
        raise ValueError("Choose --absolute-views or --relative-view, not both.")
    view_matrix, view_values = (
        _relative_views(args.relative_view, assets)
        if args.relative_view
        else (None, None)
    )
    if absolute_views is None and view_matrix is None:
        raise ValueError(
            "black_litterman requires --absolute-views or at least one --relative-view."
        )
    return BlackLittermanInputs(
        market_caps=market_caps,
        prior_returns=prior_returns,
        absolute_views=absolute_views,
        view_matrix=view_matrix,
        view_values=view_values,
        tau=args.tau,
    )


def _make_optimizer(
    args: argparse.Namespace,
    assets: pd.Index[str],
) -> Optimizer:
    """Bind the selected optimizer and its CLI configuration.

    :param args: Parsed CLI arguments.
    :param assets: Selected instrument names.
    :return: Optimizer callable for a complete historical return panel.
    """
    config = OptimizationConfig(
        periods_per_year=args.periods_per_year,
        risk_free_rate=args.risk_free_rate,
        long_only=args.long_only,
        min_weight=args.min_weight,
        max_weight=args.max_weight,
        solver=args.solver,
        risk_aversion=args.risk_aversion,
    )
    if args.strategy == "black_litterman":
        inputs = _black_litterman_inputs(args, assets)
        return lambda history: optimize_black_litterman(
            history, inputs=inputs, config=config
        )
    optimizers: dict[str, Optimizer] = {
        "max_sharpe": lambda history: max_sharpe(history, config=config),
        "min_volatility": lambda history: min_volatility(history, config=config),
        "max_quadratic_utility": lambda history: max_quadratic_utility(
            history, config=config
        ),
        "efficient_risk": lambda history: efficient_risk(
            history, target_volatility=float(args.target_volatility), config=config
        ),
        "efficient_return": lambda history: efficient_return(
            history, target_return=float(args.target_return), config=config
        ),
        "min_cvar": lambda history: min_cvar(
            history, beta=args.cvar_beta, config=config
        ),
        "efficient_cvar": lambda history: efficient_cvar(
            history,
            target_return=float(args.target_return),
            beta=args.cvar_beta,
            config=config,
        ),
        "min_semivariance": lambda history: min_semivariance(history, config=config),
        "efficient_semivariance": lambda history: efficient_semivariance(
            history, target_return=float(args.target_return), config=config
        ),
        "hrp": lambda history: optimize_hrp(history, config=config),
    }
    return optimizers[args.strategy]


def _validate_required_arguments(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> None:
    """Reject missing strategy targets and explicit Black-Litterman inputs.

    :param args: Parsed CLI options.
    :param parser: Parser used to report configuration errors.
    :raises SystemExit: If a strategy-required argument was omitted.
    """
    target_options = {
        "efficient_risk": (args.target_volatility, "--target-volatility"),
        "efficient_return": (args.target_return, "--target-return"),
        "efficient_cvar": (args.target_return, "--target-return"),
        "efficient_semivariance": (args.target_return, "--target-return"),
    }
    if args.strategy in target_options:
        target, option = target_options[args.strategy]
        if target is None:
            parser.error(f"{option} is required for strategy {args.strategy}.")
    if args.strategy == "black_litterman":
        if (args.market_caps is None) == (args.prior_returns is None):
            parser.error(
                "black_litterman requires exactly one of --market-caps or "
                "--prior-returns."
            )
        if (args.absolute_views is None) == (not args.relative_view):
            parser.error(
                "black_litterman requires either --absolute-views or "
                "--relative-view, but not both."
            )


def _metrics(
    returns: pd.Series[float], periods_per_year: int, risk_free_rate: float
) -> dict[str, float]:
    """Calculate all eight standardized metrics, marking undefined ratios NaN.

    :param returns: Portfolio simple-return observations.
    :param periods_per_year: Annualization frequency.
    :param risk_free_rate: Annual risk-free rate.
    :return: Metric values keyed by their standardized names.
    """
    calculations: dict[str, Callable[[], float]] = {
        "cumulative_return": lambda: cumulative_return(returns),
        "annualized_return": lambda: annualized_return(
            returns, periods_per_year=periods_per_year
        ),
        "realized_volatility": lambda: realized_volatility(returns),
        "annualized_realized_volatility": lambda: annualized_realized_volatility(
            returns, periods_per_year=periods_per_year
        ),
        "sharpe_ratio": lambda: sharpe_ratio(
            returns,
            periods_per_year=periods_per_year,
            risk_free_rate=risk_free_rate,
        ),
        "annualized_sharpe_ratio": lambda: annualized_sharpe_ratio(
            returns,
            periods_per_year=periods_per_year,
            risk_free_rate=risk_free_rate,
        ),
        "sortino_ratio": lambda: sortino_ratio(
            returns,
            periods_per_year=periods_per_year,
            risk_free_rate=risk_free_rate,
        ),
        "annualized_sortino_ratio": lambda: annualized_sortino_ratio(
            returns,
            periods_per_year=periods_per_year,
            risk_free_rate=risk_free_rate,
        ),
    }
    results: dict[str, float] = {}
    for name, calculation in calculations.items():
        try:
            value = calculation()
        except ValueError:
            value = float("nan")
        results[name] = value if math.isfinite(value) else float("nan")
    return results


def _rolling_windows(
    returns: pd.DataFrame,
    rolling_start: pd.Timestamp,
    rolling_end: pd.Timestamp,
    train_years: int,
    validation_years: int,
) -> list[_ValidationWindow]:
    """Create disjoint validation windows with exclusively earlier training.

    :param returns: Complete common-calendar asset returns.
    :param rolling_start: Earliest date admitted to a training window.
    :param rolling_end: Inclusive final validation date.
    :param train_years: Trailing training-window duration in calendar years.
    :param validation_years: Maximum validation-window duration in years.
    :return: Chronological validation windows and their prior training panels.
    """
    candidate = rolling_start + pd.DateOffset(years=train_years)
    dates = pd.DatetimeIndex(returns.index)
    position = int(dates.searchsorted(candidate, side="left"))
    windows: list[_ValidationWindow] = []
    while position < len(dates) and dates[position] <= rolling_end:
        start = pd.Timestamp(dates[position])
        end = min(
            start + pd.DateOffset(years=validation_years) - pd.Timedelta(days=1),
            rolling_end,
        )
        train_start = start - pd.DateOffset(years=train_years)
        training = returns.loc[(returns.index >= train_start) & (returns.index < start)]
        validation = returns.loc[(returns.index >= start) & (returns.index <= end)]
        if len(training) < _MIN_TRAINING_OBSERVATIONS or validation.empty:
            raise ValueError(
                f"Insufficient training or validation data for window starting {start.date()}."
            )
        windows.append(_ValidationWindow(start, end, training, validation))
        position = int(dates.searchsorted(end, side="right"))
    if not windows:
        raise ValueError(
            "No validation window fits; provide more history or adjust the rolling dates."
        )
    return windows


def _portfolio_returns(
    asset_returns: pd.DataFrame, weights: pd.Series[float]
) -> pd.Series[float]:
    """Aggregate asset simple returns using fixed weights for one test window.

    :param asset_returns: Test returns, disjoint from optimizer training data.
    :param weights: Optimized weights indexed by asset name.
    :return: Fixed-weight portfolio simple returns.
    """
    result = asset_returns.mul(weights, axis="columns").sum(axis=1)
    result.name = "portfolio_return"
    if (
        not np.isfinite(result.to_numpy(dtype=float)).all()
        or ((1.0 + result.to_numpy(dtype=float)) <= 0.0).any()
    ):
        raise ValueError("Portfolio value became non-positive in a test window.")
    return result


def _metric_table(
    returns: pd.Series[float],
    metric_names: list[str],
    periods_per_year: int,
    risk_free_rate: float,
) -> pd.DataFrame:
    """Build a one-row table containing requested standardized metrics.

    :param returns: Portfolio simple-return observations.
    :param metric_names: Requested report metrics.
    :param periods_per_year: Annualization frequency.
    :param risk_free_rate: Annual risk-free rate.
    :return: DataFrame containing one record per test period.
    """
    calculated = _metrics(returns, periods_per_year, risk_free_rate)
    return pd.DataFrame([{name: calculated[name] for name in metric_names}])


def _validation_report(
    windows: list[_ValidationWindow],
    optimizer: Optimizer,
    metric_names: list[str],
    periods_per_year: int,
    risk_free_rate: float,
) -> pd.DataFrame:
    """Calculate requested metrics over each disjoint validation window.

    :param windows: Chronological windows with separate training and test rows.
    :param optimizer: Strategy optimizer fitted independently per window.
    :param metric_names: Report metrics to retain.
    :param periods_per_year: Annualization frequency.
    :param risk_free_rate: Annual risk-free rate.
    :return: Metrics indexed by validation-window dates.
    """
    records: list[dict[str, float]] = []
    labels: list[str] = []
    for number, window in enumerate(windows, start=1):
        weights = optimizer(window.training).weights
        test_returns = _portfolio_returns(window.validation, weights)
        table = _metric_table(
            test_returns, metric_names, periods_per_year, risk_free_rate
        )
        records.append({name: float(table.iloc[0][name]) for name in metric_names})
        labels.append(f"{number}: {window.start.date()} to {window.end.date()}")
    return pd.DataFrame(records, index=labels)


def _fit_out_of_sample(
    returns: pd.DataFrame,
    common_dates: pd.DatetimeIndex,
    args: argparse.Namespace,
    rolling_end: pd.Timestamp,
    optimizer: Optimizer,
) -> tuple[pd.Series[float], pd.Series[float], pd.Timestamp]:
    """Fit on prior data and calculate fixed-weight OOS portfolio returns.

    :param returns: Complete common-calendar asset returns.
    :param common_dates: Complete common-calendar price dates.
    :param args: Parsed CLI date and training options.
    :param rolling_end: Inclusive end of the validation schedule.
    :param optimizer: Strategy optimizer.
    :raises ValueError: If OOS dates or required prior observations are absent.
    :return: Final weights, OOS portfolio returns, and effective OOS start.
    """
    oos_start = _effective_date(
        args.oos_start,
        common_dates,
        rolling_end + pd.Timedelta(days=1),
        "--oos-start",
    )
    if oos_start <= rolling_end:
        raise ValueError("--oos-start must be after the validation rolling end.")
    oos_end = args.oos_end or pd.Timestamp(common_dates[-1])
    if oos_end < oos_start:
        raise ValueError("--oos-end must not be earlier than --oos-start.")
    oos_returns = returns.loc[(returns.index >= oos_start) & (returns.index <= oos_end)]
    if oos_returns.empty:
        raise ValueError("The out-of-sample interval contains no common returns.")
    training_start = oos_start - pd.DateOffset(years=args.train_years)
    final_training = returns.loc[
        (returns.index >= training_start) & (returns.index < oos_start)
    ]
    if len(final_training) < _MIN_TRAINING_OBSERVATIONS:
        raise ValueError("Insufficient prior observations to fit final weights.")
    final_weights = optimizer(final_training).weights
    return final_weights, _portfolio_returns(oos_returns, final_weights), oos_start


def _effective_date(
    requested: pd.Timestamp | None,
    dates: pd.DatetimeIndex,
    default: pd.Timestamp,
    label: str,
) -> pd.Timestamp:
    """Choose the first common trading date on or after a requested date.

    :param requested: Explicit calendar date, or ``None``.
    :param dates: Ordered common price dates.
    :param default: Date used when no explicit value was supplied.
    :param label: Name used in validation errors.
    :raises ValueError: If no common date follows the requested date.
    :return: Effective common trading date.
    """
    target = requested or default
    position = int(dates.searchsorted(target, side="left"))
    if position >= len(dates):
        raise ValueError(f"No common trading date on or after {label} {target.date()}.")
    return pd.Timestamp(dates[position])


def _report(
    returns: pd.DataFrame,
    common_dates: pd.DatetimeIndex,
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> None:
    """Run validation windows, fit final weights, and print OOS performance.

    :param returns: Complete common-calendar asset returns.
    :param common_dates: Complete common-calendar price dates.
    :param args: Parsed CLI options.
    :param parser: Parser used for argument error reporting.
    :raises SystemExit: If requested periods or metrics are invalid.
    """
    metric_names = [name.strip() for name in args.metrics.split(",") if name.strip()]
    if not metric_names or any(name not in METRIC_NAMES for name in metric_names):
        parser.error(f"--metrics must contain only: {', '.join(METRIC_NAMES)}.")
    latest = pd.Timestamp(common_dates[-1])
    start = args.rolling_start or pd.Timestamp(common_dates[0])
    end = args.rolling_end or (
        latest - pd.DateOffset(years=args.validation_years) - pd.Timedelta(days=1)
    )
    if start >= end:
        parser.error("--rolling-start must be earlier than --rolling-end.")
    if end > latest:
        parser.error("--rolling-end must not be later than the latest common date.")
    try:
        windows = _rolling_windows(
            returns, start, end, args.train_years, args.validation_years
        )
        optimizer = _make_optimizer(args, returns.columns)
        validation = _validation_report(
            windows,
            optimizer,
            metric_names,
            args.periods_per_year,
            args.risk_free_rate,
        )
        final_weights, final_returns, oos_start = _fit_out_of_sample(
            returns, common_dates, args, end, optimizer
        )
    except (ValueError, RuntimeError) as error:
        parser.error(str(error))

    sys.stdout.write("Final portfolio weights (fit only on data before OOS start):\n")
    sys.stdout.write(
        final_weights.sort_index().to_frame("weight").to_string(float_format="%.6f")
        + "\n"
    )
    sys.stdout.write("\nValidation-window metrics:\n")
    sys.stdout.write(validation.to_string(float_format="%.6f") + "\n")
    averages = validation.mean(axis=0)
    sys.stdout.write("\nValidation-window metric averages:\n")
    sys.stdout.write(averages.to_frame("average").to_string(float_format="%.6f") + "\n")
    out_of_sample = _metric_table(
        final_returns,
        metric_names,
        args.periods_per_year,
        args.risk_free_rate,
    )
    out_of_sample.index = [f"{oos_start.date()} to {final_returns.index[-1].date()}"]
    sys.stdout.write("\nOut-of-sample metrics:\n")
    sys.stdout.write(out_of_sample.to_string(float_format="%.6f") + "\n")
    sys.stdout.write(
        "\nMetric convention: simple portfolio returns; unannualized ratios are "
        "per-observation, annualized ratios use sqrt(periods_per_year). Target "
        "weights are held fixed within each test window; transaction costs are "
        "not modeled.\n"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the rolling validation and out-of-sample CLI.

    :param argv: Optional arguments, excluding the program name.
    :raises SystemExit: If command-line arguments or input data are invalid.
    :return: Successful process status.
    """
    parser = _parser()
    args = parser.parse_args(argv)
    _validate_required_arguments(args, parser)
    try:
        prices = load_price_panel(
            args.data_dir,
            instruments=(
                sorted(Path(filename).stem for filename in args.instruments)
                if args.instruments is not None
                else None
            ),
        )
        common_prices = align_prices(prices, policy="inner")
        returns = prices_to_returns(
            common_prices, method="simple", alignment_policy="inner"
        )
    except (FileNotFoundError, ValueError) as error:
        parser.error(str(error))
    if args.periods_per_year < 1:
        parser.error("--periods-per-year must be positive.")
    _report(returns, pd.DatetimeIndex(common_prices.index), args, parser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
