"""Typed PyPortfolioOpt wrappers with explicit estimation assumptions."""

from __future__ import annotations

import importlib
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol, cast

import numpy as np
import pandas as pd
from scipy.cluster import hierarchy
from scipy.spatial.distance import squareform

_MIN_OBSERVATIONS = 2
_COVARIANCE_TOLERANCE = 1e-9
_WEIGHT_SUM_TOLERANCE = 1e-8
_WEIGHT_BOUND_TOLERANCE = 1e-6
_NORMALIZATION_EPSILON = 1e-12


class OptimizationError(RuntimeError):
    """Raised when an optimizer fails or returns invalid portfolio weights."""


@dataclass(frozen=True)
class OptimizationConfig:
    """Annualization, alignment, estimation, cost, solver, and weight assumptions.

    :ivar periods_per_year: Return observations per year used to annualize
        expected returns and covariance.
    :ivar risk_free_rate: Annual risk-free rate in decimal units.
    :ivar alignment_policy: How input calendars were aligned before returns
        were calculated.
    :ivar ffill_limit: Required maximum age in rows when alignment uses
        forward-filling; otherwise ``None``.
    :ivar estimation_window: Most recent number of complete return rows to use,
        or ``None`` to use the full available common history.
    :ivar long_only: Whether short positions are prohibited.
    :ivar min_weight: Optional lower bound per asset; defaults to zero for
        long-only portfolios and -1 for portfolios allowing short sales.
    :ivar max_weight: Maximum weight per asset.
    :ivar rebalancing_frequency: Planned frequency used by walk-forward
        backtests.
    :ivar transaction_cost_bps: Linear transaction cost used by backtests.
    :ivar solver: Optional CVXPY solver name; ``None`` uses the library default.
    :ivar risk_aversion: Positive quadratic utility and Black-Litterman
        risk-aversion coefficient.
    """

    periods_per_year: int = 252
    risk_free_rate: float = 0.0
    alignment_policy: str = "inner"
    ffill_limit: int | None = None
    estimation_window: int | None = None
    long_only: bool = True
    min_weight: float | None = None
    max_weight: float = 1.0
    rebalancing_frequency: str = "M"
    transaction_cost_bps: float = 0.0
    solver: str | None = None
    risk_aversion: float = 1.0


_DEFAULT_CONFIG = OptimizationConfig()


@dataclass(frozen=True)
class OptimizationResult:
    """Normalized weights, assumptions, and limitations from an optimizer.

    :ivar weights: Asset weights, ordered by instrument, normalized to sum to 1.
    :ivar strategy: Name of the optimization strategy used.
    :ivar assumptions: Scalar assumptions used for estimation.
    :ivar limitations: Known data and inference limitations to show with results.
    """

    weights: pd.Series[float]
    strategy: str
    assumptions: Mapping[str, str | int | float | bool | None]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class _Request:
    """Internal optimizer method and its optional target parameters."""

    method: str
    target_return: float | None = None
    target_volatility: float | None = None
    beta: float = 0.95


@dataclass(frozen=True)
class _Estimates:
    """Complete sample window and its annualized mean/covariance estimates."""

    returns: pd.DataFrame
    expected: pd.Series[float]
    covariance: pd.DataFrame


@dataclass(frozen=True)
class BlackLittermanInputs:
    """Explicit prior and view inputs for Black-Litterman optimization.

    :ivar market_caps: Positive capitalization data for an implied prior.
    :ivar prior_returns: Annual prior returns, alternatively to ``market_caps``.
    :ivar absolute_views: Named annual return views, or ``None``.
    :ivar view_matrix: Linear view matrix, or ``None``.
    :ivar view_values: Annual returns for rows of ``view_matrix``.
    :ivar tau: Positive uncertainty scalar for prior covariance.
    """

    market_caps: pd.Series[float] | None = None
    prior_returns: pd.Series[float] | None = None
    absolute_views: pd.Series[float] | None = None
    view_matrix: pd.DataFrame | None = None
    view_values: pd.Series[float] | None = None
    tau: float = 0.05


@dataclass(frozen=True)
class _BLRequest:
    """Validated Black-Litterman prior and view arguments."""

    prior: pd.Series[float]
    view_kwargs: dict[str, object]
    view_type: str
    tau: float
    market_caps: pd.Series[float] | None


class _Frontier(Protocol):
    """Methods shared by the PyPortfolioOpt frontier classes used here."""

    weights: np.ndarray

    def max_sharpe(self, risk_free_rate: float = 0.0) -> object: ...

    def min_volatility(self) -> object: ...

    def efficient_risk(self, target_volatility: float) -> object: ...

    def efficient_return(self, target_return: float) -> object: ...

    def max_quadratic_utility(self, risk_aversion: float = 1.0) -> object: ...

    def min_cvar(self) -> object: ...

    def min_semivariance(self) -> object: ...


class _HRP(Protocol):
    """HRP result surface used by this module."""

    weights: np.ndarray

    def optimize(self) -> object: ...


class _BlackLitterman(Protocol):
    """Black-Litterman result surface used by this module."""

    def bl_weights(self, risk_aversion: float | None = None) -> Mapping[str, float]: ...


def _validate_config_fields(config: OptimizationConfig) -> None:
    """Validate shared settings that do not depend on the number of assets.

    :param config: Optimizer assumptions.
    :raises ValueError: If an assumption is outside its valid domain.
    """
    _validate_annualization(config)
    _validate_simulation_config(config)
    if config.alignment_policy not in {"inner", "ffill"}:
        raise ValueError("alignment_policy must be 'inner' or 'ffill'.")
    if config.alignment_policy == "ffill" and (
        config.ffill_limit is None or config.ffill_limit < 1
    ):
        raise ValueError("ffill_limit must be positive for ffill alignment.")
    if config.alignment_policy == "inner" and config.ffill_limit is not None:
        raise ValueError("ffill_limit is only valid for ffill alignment.")
    if (
        config.estimation_window is not None
        and config.estimation_window < _MIN_OBSERVATIONS
    ):
        raise ValueError("estimation_window must be at least 2.")


def _validate_annualization(config: OptimizationConfig) -> None:
    """Validate periods and risk-free assumptions.

    :param config: Optimizer assumptions.
    :raises ValueError: If annualization values are invalid.
    """
    if isinstance(config.periods_per_year, bool) or config.periods_per_year < 1:
        raise ValueError("periods_per_year must be a positive integer.")
    if not math.isfinite(config.risk_free_rate) or config.risk_free_rate <= -1.0:
        raise ValueError("risk_free_rate must be finite and greater than -1.")


def _validate_simulation_config(config: OptimizationConfig) -> None:
    """Validate planned rebalancing, cost, and risk-aversion assumptions.

    :param config: Optimizer assumptions.
    :raises ValueError: If cost or risk aversion is invalid.
    """
    if not config.rebalancing_frequency:
        raise ValueError("rebalancing_frequency must be a non-empty period string.")
    if (
        not math.isfinite(config.transaction_cost_bps)
        or config.transaction_cost_bps < 0
    ):
        raise ValueError("transaction_cost_bps must be finite and non-negative.")
    if not math.isfinite(config.risk_aversion) or config.risk_aversion <= 0.0:
        raise ValueError("risk_aversion must be finite and positive.")


def _bounds_for(n_assets: int, config: OptimizationConfig) -> tuple[float, float]:
    """Validate portfolio bounds and return effective scalar limits.

    :param n_assets: Number of assets to optimize.
    :param config: Weight-bound and long-only assumptions.
    :raises ValueError: If bounds are invalid or cannot sum to one.
    :return: Lower and upper per-asset weights.
    """
    _validate_config_fields(config)
    lower = config.min_weight
    if lower is None:
        lower = 0.0 if config.long_only else -1.0
    upper = config.max_weight
    if not math.isfinite(lower) or not math.isfinite(upper) or lower > upper:
        raise ValueError(
            "Weight bounds must be finite and lower must not exceed upper."
        )
    if config.long_only and lower < 0.0:
        raise ValueError("Long-only portfolios cannot have a negative minimum weight.")
    if upper > 1.0:
        raise ValueError("max_weight must not exceed 1.")
    if n_assets * lower > 1.0 or n_assets * upper < 1.0:
        raise ValueError("Weight bounds are infeasible for a fully invested portfolio.")
    return float(lower), float(upper)


def _validate_return_panel(returns: pd.DataFrame) -> None:
    """Validate the structure and simple-return domain of an input panel.

    :param returns: Simple-return panel.
    :raises ValueError: If the panel, labels, dates, or return values are invalid.
    """
    if returns.empty or len(returns.columns) == 0:
        raise ValueError("returns must contain at least one asset and observation.")
    if not returns.columns.is_unique or any(
        not isinstance(column, str) or not column for column in returns.columns
    ):
        raise ValueError("returns must have unique non-empty string asset columns.")
    _validate_return_index(returns.index)
    _validate_return_values(returns)


def _validate_return_index(index: pd.Index) -> None:
    """Validate a return panel's optional datetime index.

    :param index: Return dates.
    :raises ValueError: If a datetime index is unsorted, repeated, or timezone-aware.
    """
    if isinstance(index, pd.DatetimeIndex) and (
        index.tz is not None or not index.is_monotonic_increasing or not index.is_unique
    ):
        raise ValueError(
            "returns require a sorted, unique, timezone-naive DatetimeIndex."
        )


def _validate_return_values(returns: pd.DataFrame) -> None:
    """Validate observed simple return values.

    :param returns: Return panel.
    :raises ValueError: If any observed value is infinite or at most -100%.
    """
    values = returns.to_numpy(dtype=float)
    if np.isinf(values).any():
        raise ValueError("returns must not contain infinite values.")
    observed = values[~np.isnan(values)]
    if (observed <= -1.0).any():
        raise ValueError("Simple returns must be greater than -1.")


def _estimate(returns: pd.DataFrame, config: OptimizationConfig) -> _Estimates:
    """Estimate annualized arithmetic expected returns and sample covariance.

    Incomplete calendars are restricted to complete cases; only the last
    ``estimation_window`` complete observations are used when configured.

    :param returns: Simple-return panel.
    :param config: Annualization and estimation-window assumptions.
    :raises ValueError: If data is invalid, insufficient, or covariance is not PSD.
    :return: Complete return window and annualized estimates.
    """
    _validate_return_panel(returns)
    _bounds_for(len(returns.columns), config)
    complete = returns.astype(float).dropna(axis=0, how="any")
    if config.estimation_window is not None:
        complete = complete.tail(config.estimation_window)
    if len(complete) < _MIN_OBSERVATIONS:
        raise ValueError("At least two complete return observations are required.")
    if not np.isfinite(complete.to_numpy(dtype=float)).all():
        raise ValueError("Complete returns must be finite.")
    expected = complete.mean() * config.periods_per_year
    covariance = complete.cov() * config.periods_per_year
    eigenvalues = np.linalg.eigvalsh(covariance.to_numpy(dtype=float))
    if float(eigenvalues.min()) < -_COVARIANCE_TOLERANCE:
        raise ValueError("Estimated covariance matrix is not positive semidefinite.")
    return _Estimates(complete, expected, covariance)


def _create_frontier(
    estimates: _Estimates,
    config: OptimizationConfig,
    request: _Request,
    bounds: tuple[float, float],
) -> _Frontier:
    """Create the appropriate PyPortfolioOpt efficient frontier object.

    :param estimates: Complete returns and annualized expected returns/covariance.
    :param config: Solver and frequency assumptions.
    :param request: Optimization objective.
    :param bounds: Lower and upper portfolio bounds.
    :raises OptimizationError: If the PyPortfolioOpt class cannot be initialized.
    :return: Unsolved optimizer instance.
    """
    library = importlib.import_module("pypfopt")
    kwargs: dict[str, object] = {"weight_bounds": bounds, "solver": config.solver}
    try:
        if request.method in {"min_cvar", "efficient_cvar"}:
            factory = cast(Callable[..., _Frontier], library.EfficientCVaR)
            return factory(
                estimates.expected, estimates.returns, beta=request.beta, **kwargs
            )
        if request.method in {"min_semivariance", "efficient_semivariance"}:
            factory = cast(Callable[..., _Frontier], library.EfficientSemivariance)
            return factory(
                estimates.expected,
                estimates.returns,
                frequency=config.periods_per_year,
                **kwargs,
            )
        factory = cast(Callable[..., _Frontier], library.EfficientFrontier)
        return factory(estimates.expected, estimates.covariance, **kwargs)
    except Exception as error:
        raise OptimizationError(
            "Unable to initialize the requested optimizer."
        ) from error


def _run_objective(
    optimizer: _Frontier, request: _Request, config: OptimizationConfig
) -> None:
    """Solve one objective, requiring any strategy-specific target explicitly.

    :param optimizer: Instantiated PyPortfolioOpt model.
    :param request: Method name and optional required targets.
    :param config: Risk-free rate and risk-aversion assumptions.
    :raises OptimizationError: If the solver fails.
    :raises ValueError: If an objective target is missing or invalid.
    """
    try:
        if request.method == "max_sharpe":
            optimizer.max_sharpe(risk_free_rate=config.risk_free_rate)
        elif request.method in {"min_volatility", "min_cvar", "min_semivariance"}:
            cast(Callable[[], object], getattr(optimizer, request.method))()
        elif request.method in {
            "efficient_risk",
            "efficient_return",
            "efficient_cvar",
            "efficient_semivariance",
        }:
            _run_target_objective(optimizer, request)
        elif request.method == "max_quadratic_utility":
            optimizer.max_quadratic_utility(risk_aversion=config.risk_aversion)
        else:
            raise ValueError(f"Unknown optimization method: {request.method}.")
    except ValueError:
        raise
    except Exception as error:
        raise OptimizationError(
            f"PyPortfolioOpt failed while running {request.method}."
        ) from error


def _run_target_objective(optimizer: _Frontier, request: _Request) -> None:
    """Run an efficient objective after validating its required target.

    :param optimizer: Instantiated PyPortfolioOpt model.
    :param request: Efficient objective and its target value.
    :raises ValueError: If the required target is missing or invalid.
    """
    if request.method == "efficient_risk":
        target = request.target_volatility
        if target is None or not math.isfinite(target) or target <= 0:
            raise ValueError("target_volatility must be finite and positive.")
        optimizer.efficient_risk(target)
        return
    target_return = request.target_return
    if target_return is None or not math.isfinite(target_return):
        raise ValueError("target_return must be finite and explicitly supplied.")
    optimizer.efficient_return(target_return)


def _make_result(
    raw_weights: object,
    assets: pd.Index[str],
    strategy: str,
    config: OptimizationConfig,
    estimates: _Estimates,
) -> OptimizationResult:
    """Normalize and validate a solver result.

    :param raw_weights: Raw numeric weights returned by PyPortfolioOpt.
    :param assets: Asset labels in solver order.
    :param strategy: Objective name.
    :param config: Optimization assumptions.
    :param estimates: Data used for expected-return and covariance estimates.
    :raises OptimizationError: If weights are invalid or violate bounds.
    :return: Normalized weights, assumptions, and data limitations.
    """
    weights = np.asarray(raw_weights, dtype=float).reshape(-1)
    if len(weights) != len(assets) or not np.isfinite(weights).all():
        raise OptimizationError("Optimizer returned missing or non-finite weights.")
    total = float(weights.sum())
    if abs(total) < _NORMALIZATION_EPSILON:
        raise OptimizationError("Optimizer returned weights that cannot be normalized.")
    weights = weights / total
    lower, upper = _bounds_for(len(assets), config)
    if not np.isclose(weights.sum(), 1.0, atol=_WEIGHT_SUM_TOLERANCE):
        raise OptimizationError("Optimizer weights do not sum to one.")
    if (weights < lower - _WEIGHT_BOUND_TOLERANCE).any() or (
        weights > upper + _WEIGHT_BOUND_TOLERANCE
    ).any():
        raise OptimizationError("Optimizer returned weights outside configured bounds.")
    series = pd.Series(weights, index=assets, dtype=float, name="weight")
    assumptions: dict[str, str | int | float | bool | None] = {
        "periods_per_year": config.periods_per_year,
        "risk_free_rate": config.risk_free_rate,
        "alignment_policy": config.alignment_policy,
        "ffill_limit": config.ffill_limit,
        "estimation_window": config.estimation_window,
        "estimation_observations": len(estimates.returns),
        "long_only": config.long_only,
        "min_weight": lower,
        "max_weight": upper,
        "rebalancing_frequency": config.rebalancing_frequency,
        "transaction_cost_bps": config.transaction_cost_bps,
        "solver": config.solver,
    }
    caveats = (
        "Estimates use only the selected complete-case return window.",
        "Short ETF histories and omitted/delisted instruments can create "
        "survivorship and selection bias.",
        "Currency conversion and dividend reinvestment are not inferred by "
        "the optimizer; verify homogeneous currency and adjusted prices.",
        "Past performance does not predict future returns.",
    )
    return OptimizationResult(series, strategy, assumptions, caveats)


def _include_objective_assumptions(
    result: OptimizationResult, request: _Request
) -> OptimizationResult:
    """Attach strategy target assumptions to an optimization result.

    :param result: Validated portfolio result.
    :param request: Objective and target parameters used.
    :return: Result with objective-specific assumptions.
    """
    assumptions = dict(result.assumptions)
    assumptions["target_return"] = request.target_return
    assumptions["target_volatility"] = request.target_volatility
    if request.method in {"min_cvar", "efficient_cvar"}:
        assumptions["cvar_beta"] = request.beta
    return OptimizationResult(
        result.weights, result.strategy, assumptions, result.limitations
    )


def _optimize_frontier(
    returns: pd.DataFrame,
    config: OptimizationConfig,
    request: _Request,
) -> OptimizationResult:
    """Estimate inputs, solve a frontier objective, and normalize its weights.

    :param returns: Aligned simple returns.
    :param config: Explicit assumptions and constraints.
    :param request: Objective and optional target.
    :raises ValueError: If estimation inputs, targets, or constraints are invalid.
    :return: Validated portfolio result.
    """
    estimates = _estimate(returns, config)
    bounds = _bounds_for(len(estimates.returns.columns), config)
    if not 0.0 < request.beta < 1.0:
        raise ValueError("beta must be strictly between zero and one.")
    optimizer = _create_frontier(estimates, config, request, bounds)
    _run_objective(optimizer, request, config)
    result = _make_result(
        optimizer.weights,
        estimates.returns.columns,
        request.method,
        config,
        estimates,
    )
    return _include_objective_assumptions(result, request)


def min_volatility(
    returns: pd.DataFrame, *, config: OptimizationConfig = _DEFAULT_CONFIG
) -> OptimizationResult:
    """Minimize annualized portfolio variance under configured weight bounds.

    :param returns: Aligned panel of simple asset returns.
    :param config: Periods, alignment, estimation window, solver, and constraints.
    :return: Minimum-volatility portfolio result.
    """
    return _optimize_frontier(returns, config, _Request("min_volatility"))


def max_sharpe(
    returns: pd.DataFrame, *, config: OptimizationConfig = _DEFAULT_CONFIG
) -> OptimizationResult:
    """Maximize estimated Sharpe ratio using the configured annual risk-free rate.

    :param returns: Aligned panel of simple asset returns.
    :param config: Periods, risk-free rate, estimation window, and bounds.
    :return: Maximum-Sharpe portfolio result.
    """
    return _optimize_frontier(returns, config, _Request("max_sharpe"))


def efficient_risk(
    returns: pd.DataFrame,
    *,
    target_volatility: float,
    config: OptimizationConfig = _DEFAULT_CONFIG,
) -> OptimizationResult:
    """Maximize expected return for a required annual target volatility.

    :param returns: Aligned panel of simple asset returns.
    :param target_volatility: Required positive annual volatility target.
    :param config: Periods, estimation window, and constraints.
    :return: Efficient-risk portfolio result.
    """
    return _optimize_frontier(
        returns,
        config,
        _Request("efficient_risk", target_volatility=target_volatility),
    )


def efficient_return(
    returns: pd.DataFrame,
    *,
    target_return: float,
    config: OptimizationConfig = _DEFAULT_CONFIG,
) -> OptimizationResult:
    """Minimize volatility for a required annual expected-return target.

    :param returns: Aligned panel of simple returns.
    :param target_return: Required annual expected return; there is no fallback.
    :param config: Periods, estimation window, and constraints.
    :return: Efficient-return portfolio result.
    """
    return _optimize_frontier(
        returns, config, _Request("efficient_return", target_return=target_return)
    )


def max_quadratic_utility(
    returns: pd.DataFrame, *, config: OptimizationConfig = _DEFAULT_CONFIG
) -> OptimizationResult:
    """Maximize mean-variance utility using configured risk aversion.

    :param returns: Aligned panel of simple asset returns.
    :param config: Periods, risk aversion, estimation window, and bounds.
    :return: Maximum-quadratic-utility portfolio result.
    """
    return _optimize_frontier(returns, config, _Request("max_quadratic_utility"))


def min_cvar(
    returns: pd.DataFrame,
    *,
    beta: float = 0.95,
    config: OptimizationConfig = _DEFAULT_CONFIG,
) -> OptimizationResult:
    """Minimize historical Conditional Value at Risk.

    :param returns: Aligned panel of simple returns.
    :param beta: CVaR confidence level strictly between zero and one.
    :param config: Periods, estimation window, solver, and bounds.
    :return: Minimum-CVaR portfolio result.
    """
    return _optimize_frontier(returns, config, _Request("min_cvar", beta=beta))


def efficient_cvar(
    returns: pd.DataFrame,
    *,
    target_return: float,
    beta: float = 0.95,
    config: OptimizationConfig = _DEFAULT_CONFIG,
) -> OptimizationResult:
    """Minimize CVaR for a required annual expected-return target.

    :param returns: Aligned panel of simple returns.
    :param target_return: Required annual expected return; no default is used.
    :param beta: CVaR confidence level strictly between zero and one.
    :param config: Periods, estimation window, solver, and bounds.
    :return: Efficient-CVaR portfolio result.
    """
    return _optimize_frontier(
        returns,
        config,
        _Request("efficient_cvar", target_return=target_return, beta=beta),
    )


def min_semivariance(
    returns: pd.DataFrame, *, config: OptimizationConfig = _DEFAULT_CONFIG
) -> OptimizationResult:
    """Minimize downside semivariance with zero as benchmark return.

    :param returns: Aligned panel of simple returns.
    :param config: Periods, estimation window, solver, and bounds.
    :return: Minimum-semivariance portfolio result.
    """
    return _optimize_frontier(returns, config, _Request("min_semivariance"))


def efficient_semivariance(
    returns: pd.DataFrame,
    *,
    target_return: float,
    config: OptimizationConfig = _DEFAULT_CONFIG,
) -> OptimizationResult:
    """Minimize semivariance for a required annual expected-return target.

    :param returns: Aligned panel of simple returns.
    :param target_return: Required annual expected return; no default is used.
    :param config: Periods, estimation window, solver, and bounds.
    :return: Efficient-semivariance portfolio result.
    """
    return _optimize_frontier(
        returns,
        config,
        _Request("efficient_semivariance", target_return=target_return),
    )


def optimize_hrp(
    returns: pd.DataFrame, *, config: OptimizationConfig = _DEFAULT_CONFIG
) -> OptimizationResult:
    """Calculate Hierarchical Risk Parity weights from historical returns.

    :param returns: Aligned panel of simple returns.
    :param config: Periods, estimation window, and constraints.
    :raises OptimizationError: If HRP fails or violates configured bounds.
    :return: Normalized HRP portfolio result.
    """
    estimates = _estimate(returns, config)
    _bounds_for(len(estimates.returns.columns), config)
    library = importlib.import_module("pypfopt")
    factory = cast(Callable[..., _HRP], library.HRPOpt)
    try:
        optimizer = factory(returns=estimates.returns, cov_matrix=estimates.covariance)
        if hasattr(hierarchy, "_LINKAGE_METHODS"):
            optimizer.optimize()
            raw_weights: object = optimizer.weights
            backend = "PyPortfolioOpt"
        else:
            raw_weights = _hrp_weights(estimates.returns)
            backend = "public SciPy compatibility path"
    except Exception as error:
        raise OptimizationError("PyPortfolioOpt failed while running HRP.") from error
    result = _make_result(
        raw_weights, estimates.returns.columns, "hrp", config, estimates
    )
    assumptions = dict(result.assumptions)
    assumptions["implementation"] = backend
    return OptimizationResult(
        result.weights, result.strategy, assumptions, result.limitations
    )


def _hrp_weights(returns: pd.DataFrame) -> pd.Series[float]:
    """Run HRP clustering through public SciPy APIs.

    PyPortfolioOpt 1.6.0 checks SciPy's private ``_LINKAGE_METHODS`` constant,
    which was removed by recent SciPy versions. This implementation preserves
    the library's correlation distance, quasi-diagonalization, and recursive
    bisection without mutating SciPy's module.

    :param returns: Complete return window.
    :raises ValueError: If asset variances are not strictly positive.
    :return: HRP weights indexed by asset.
    """
    covariance = returns.cov()
    diagonal = np.diag(covariance.to_numpy(dtype=float))
    if (diagonal <= 0.0).any() or not np.isfinite(diagonal).all():
        raise ValueError("HRP requires finite positive asset variances.")
    if len(returns.columns) == 1:
        return pd.Series([1.0], index=returns.columns, dtype=float)
    correlation = returns.corr()
    distance = np.sqrt(
        np.clip((1.0 - correlation.to_numpy(dtype=float)) / 2.0, 0.0, 1.0)
    )
    linkage = hierarchy.linkage(squareform(distance, checks=False), method="single")
    ordered = correlation.columns[hierarchy.to_tree(linkage).pre_order()].tolist()
    weights = pd.Series(1.0, index=ordered, dtype=float)
    clusters = [ordered]
    while any(len(cluster) > 1 for cluster in clusters):
        clusters = [
            half
            for cluster in clusters
            if len(cluster) > 1
            for half in (cluster[: len(cluster) // 2], cluster[len(cluster) // 2 :])
        ]
        for offset in range(0, len(clusters), 2):
            left = clusters[offset]
            right = clusters[offset + 1]
            left_var = _cluster_variance(covariance, left)
            right_var = _cluster_variance(covariance, right)
            left_weight = 1.0 - left_var / (left_var + right_var)
            weights.loc[left] *= left_weight
            weights.loc[right] *= 1.0 - left_weight
    return weights.reindex(returns.columns)


def _cluster_variance(covariance: pd.DataFrame, assets: list[str]) -> float:
    """Calculate inverse-variance weighted cluster variance.

    :param covariance: Asset covariance matrix.
    :param assets: Names assigned to a hierarchical cluster.
    :return: Portfolio variance of the cluster's inverse-variance portfolio.
    """
    cluster = covariance.loc[assets, assets].to_numpy(dtype=float)
    cluster_weights = 1.0 / np.diag(cluster)
    cluster_weights /= cluster_weights.sum()
    return float(cluster_weights @ cluster @ cluster_weights)


def _bl_prior(
    estimates: _Estimates,
    inputs: BlackLittermanInputs,
    config: OptimizationConfig,
) -> pd.Series[float]:
    """Validate and construct the explicit Black-Litterman prior.

    :param estimates: Return estimates, used to identify assets and covariance.
    :param inputs: Explicit market-cap or expected-return prior.
    :param config: Risk aversion used for a market-implied prior.
    :raises ValueError: If the prior is missing or malformed.
    :return: Prior expected returns in asset order.
    """
    market_caps = inputs.market_caps
    prior_returns = inputs.prior_returns
    if (market_caps is None) == (prior_returns is None):
        raise ValueError("Supply exactly one of market_caps or prior_returns.")
    assets = estimates.returns.columns
    if prior_returns is not None:
        if (
            set(prior_returns.index) != set(assets)
            or not np.isfinite(prior_returns.to_numpy(dtype=float)).all()
        ):
            raise ValueError(
                "prior_returns must provide finite values for every asset."
            )
        return prior_returns.reindex(assets)
    if market_caps is None or set(market_caps.index) != set(assets):
        raise ValueError("market_caps must provide a positive value for every asset.")
    if (
        not np.isfinite(market_caps.to_numpy(dtype=float)).all()
        or (market_caps <= 0.0).any()
    ):
        raise ValueError("market_caps must be finite and positive.")
    library = importlib.import_module("pypfopt.black_litterman")
    factory = cast(
        Callable[..., object],
        library.market_implied_prior_returns,
    )
    result = factory(
        market_caps.reindex(assets),
        config.risk_aversion,
        estimates.covariance,
        risk_free_rate=config.risk_free_rate,
    )
    return pd.Series(result, index=assets, dtype=float)


def _bl_views(
    assets: pd.Index[str],
    inputs: BlackLittermanInputs,
) -> tuple[dict[str, object], str]:
    """Validate explicit absolute or matrix-form Black-Litterman views.

    :param assets: Optimized asset labels.
    :param inputs: Explicit absolute or matrix-form views.
    :raises ValueError: If views are missing or inconsistent.
    :return: PyPortfolioOpt keyword arguments and a view-kind label.
    """
    if inputs.absolute_views is not None:
        return _validate_absolute_views(assets, inputs)
    if inputs.view_matrix is None or inputs.view_values is None:
        raise ValueError(
            "Supply either absolute_views or both view_matrix and view_values."
        )
    return _validate_relative_views(assets, inputs)


def _validate_absolute_views(
    assets: pd.Index[str], inputs: BlackLittermanInputs
) -> tuple[dict[str, object], str]:
    """Validate named absolute return views.

    :param assets: Optimized asset labels.
    :param inputs: Explicit Black-Litterman inputs.
    :raises ValueError: If absolute views overlap another view format or are invalid.
    :return: Library keyword arguments and a view-kind label.
    """
    views = inputs.absolute_views
    if inputs.view_matrix is not None or inputs.view_values is not None:
        raise ValueError("Supply only one Black-Litterman view representation.")
    if views is None or not set(views.index).issubset(set(assets)):
        raise ValueError("absolute_views contain unknown or missing assets.")
    if not np.isfinite(views.to_numpy(dtype=float)).all():
        raise ValueError("absolute_views must be finite.")
    return {"absolute_views": views.to_dict()}, "absolute"


def _validate_relative_views(
    assets: pd.Index[str], inputs: BlackLittermanInputs
) -> tuple[dict[str, object], str]:
    """Validate a linear view matrix and target vector.

    :param assets: Optimized asset labels.
    :param inputs: Explicit Black-Litterman inputs.
    :raises ValueError: If matrix dimensions or view values are invalid.
    :return: Library keyword arguments and a view-kind label.
    """
    matrix = inputs.view_matrix
    values = inputs.view_values
    if matrix is None or values is None:
        raise ValueError("Both view_matrix and view_values are required.")
    if list(matrix.columns) != list(assets) or len(matrix) != len(values):
        raise ValueError(
            "view_matrix columns and rows must match assets and view_values."
        )
    if (
        not np.isfinite(matrix.to_numpy(dtype=float)).all()
        or not np.isfinite(values.to_numpy(dtype=float)).all()
    ):
        raise ValueError("Views must contain finite values.")
    return {"P": matrix, "Q": values}, "relative"


def optimize_black_litterman(
    returns: pd.DataFrame,
    *,
    inputs: BlackLittermanInputs,
    config: OptimizationConfig = _DEFAULT_CONFIG,
) -> OptimizationResult:
    """Infer Black-Litterman weights from an explicit prior and explicit views.

    Exactly one prior is required in ``inputs``: ``market_caps`` or annual
    ``prior_returns``. Supply either named ``absolute_views`` or both
    ``view_matrix`` and ``view_values``. No market caps or views are invented.

    :param returns: Aligned panel of simple returns.
    :param inputs: Required explicit prior, views, and prior uncertainty.
    :param config: Periods, risk aversion, estimation window, and constraints.
    :raises ValueError: If the prior uncertainty is invalid.
    :return: Black-Litterman weights with stated assumptions.
    """
    if not math.isfinite(inputs.tau) or inputs.tau <= 0.0:
        raise ValueError("tau must be finite and positive.")
    estimates = _estimate(returns, config)
    _bounds_for(len(estimates.returns.columns), config)
    prior = _bl_prior(estimates, inputs, config)
    view_kwargs, view_type = _bl_views(estimates.returns.columns, inputs)
    request = _BLRequest(
        prior,
        view_kwargs,
        view_type,
        inputs.tau,
        inputs.market_caps,
    )
    return _run_black_litterman(estimates, config, request)


def _run_black_litterman(
    estimates: _Estimates,
    config: OptimizationConfig,
    request: _BLRequest,
) -> OptimizationResult:
    """Run Black-Litterman and attach prior/view assumptions.

    :param estimates: Complete return window and annualized covariance.
    :param config: Risk-aversion and weight assumptions.
    :param request: Validated prior, views, and uncertainty.
    :raises OptimizationError: If optimization fails.
    :return: Black-Litterman result object.
    """
    library = importlib.import_module("pypfopt")
    factory = cast(Callable[..., _BlackLitterman], library.BlackLittermanModel)
    try:
        model = factory(
            estimates.covariance,
            pi=request.prior,
            tau=request.tau,
            **request.view_kwargs,
        )
        raw_weights = pd.Series(
            model.bl_weights(risk_aversion=config.risk_aversion), dtype=float
        )
        result = _make_result(
            raw_weights.reindex(estimates.returns.columns).to_numpy(dtype=float),
            estimates.returns.columns,
            "black_litterman",
            config,
            estimates,
        )
    except Exception as error:
        raise OptimizationError(
            "PyPortfolioOpt failed while running Black-Litterman."
        ) from error
    assumptions = dict(result.assumptions)
    assumptions.update(
        {
            "risk_aversion": config.risk_aversion,
            "tau": request.tau,
            "views": request.view_type,
            "prior": "market_caps" if request.market_caps is not None else "explicit",
        }
    )
    return OptimizationResult(
        result.weights, result.strategy, assumptions, result.limitations
    )
