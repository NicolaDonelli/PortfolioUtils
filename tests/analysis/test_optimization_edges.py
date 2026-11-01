"""Tests for optimizer objective, HRP, and Black-Litterman edge cases."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from portfolio_utils.analysis import optimization
from portfolio_utils.analysis.optimization import (
    BlackLittermanInputs,
    OptimizationConfig,
    OptimizationError,
    _bl_prior,
    _bl_views,
    _BLRequest,
    _create_frontier,
    _estimate,
    _hrp_weights,
    _Request,
    _run_black_litterman,
    _run_objective,
    optimize_black_litterman,
    optimize_hrp,
)


class _DummyFrontier:
    """Minimal protocol-complete optimizer fake."""

    weights = np.array([0.5, 0.5])

    def max_sharpe(self, _risk_free_rate: float = 0.0) -> object:
        return None

    def min_volatility(self) -> object:
        return None

    def efficient_risk(self, _target: float) -> object:
        return None

    def efficient_return(self, _target: float) -> object:
        return None

    def max_quadratic_utility(self, _risk_aversion: float = 1.0) -> object:
        return None

    def min_cvar(self) -> object:
        return None

    def min_semivariance(self) -> object:
        return None


def _returns() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "a": [-0.02, 0.01, 0.03, -0.01, 0.02, 0.00],
            "b": [0.01, -0.01, 0.00, 0.02, -0.02, 0.03],
        },
        index=pd.date_range("2024-01-01", periods=6, freq="B"),
    )


@pytest.mark.parametrize(
    ("inputs", "message"),
    [
        (BlackLittermanInputs(), "exactly one"),
        (
            BlackLittermanInputs(
                prior_returns=pd.Series({"a": 0.1}),
            ),
            "finite values for every asset",
        ),
        (
            BlackLittermanInputs(
                prior_returns=pd.Series({"a": 0.1, "b": float("inf")}),
            ),
            "finite values for every asset",
        ),
        (
            BlackLittermanInputs(
                market_caps=pd.Series({"a": 100.0}),
            ),
            "market_caps must provide",
        ),
        (
            BlackLittermanInputs(
                market_caps=pd.Series({"a": 100.0, "b": 0.0}),
            ),
            "finite and positive",
        ),
    ],
)
def test_black_litterman_rejects_bad_priors(
    inputs: BlackLittermanInputs, message: str
) -> None:
    estimates = _estimate(_returns(), OptimizationConfig())
    with pytest.raises(ValueError, match=message):
        _bl_prior(estimates, inputs, OptimizationConfig())


@pytest.mark.parametrize(
    ("inputs", "message"),
    [
        (BlackLittermanInputs(), "Supply either absolute_views"),
        (
            BlackLittermanInputs(
                absolute_views=pd.Series({"a": 0.1}),
                view_values=pd.Series([0.1]),
            ),
            "only one",
        ),
        (
            BlackLittermanInputs(absolute_views=pd.Series({"unknown": 0.1})),
            "unknown or missing",
        ),
        (
            BlackLittermanInputs(
                absolute_views=pd.Series({"a": float("nan")}),
            ),
            "absolute_views must be finite",
        ),
        (
            BlackLittermanInputs(
                view_matrix=pd.DataFrame([[1.0]], columns=["a"]),
            ),
            "both view_matrix and view_values",
        ),
        (
            BlackLittermanInputs(
                view_matrix=pd.DataFrame([[1.0]], columns=["wrong"]),
                view_values=pd.Series([0.1]),
            ),
            "columns and rows must match",
        ),
        (
            BlackLittermanInputs(
                view_matrix=pd.DataFrame([[float("inf"), 0.0]], columns=["a", "b"]),
                view_values=pd.Series([0.1]),
            ),
            "finite values",
        ),
    ],
)
def test_black_litterman_rejects_bad_views(
    inputs: BlackLittermanInputs, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _bl_views(_returns().columns, inputs)


def test_black_litterman_relative_views_are_supported() -> None:
    result = optimize_black_litterman(
        _returns(),
        inputs=BlackLittermanInputs(
            prior_returns=pd.Series({"a": 0.04, "b": 0.03}),
            view_matrix=pd.DataFrame([[1.0, -1.0]], columns=["a", "b"]),
            view_values=pd.Series([0.02]),
        ),
        config=OptimizationConfig(periods_per_year=252, solver="CLARABEL"),
    )

    assert result.assumptions["views"] == "relative"
    assert result.weights.sum() == pytest.approx(1.0, abs=1e-8)


def test_black_litterman_rejects_invalid_tau() -> None:
    for tau in (0.0, float("inf")):
        with pytest.raises(ValueError, match="tau"):
            optimize_black_litterman(
                _returns(),
                inputs=BlackLittermanInputs(
                    prior_returns=pd.Series({"a": 0.04, "b": 0.03}),
                    absolute_views=pd.Series({"a": 0.05}),
                    tau=tau,
                ),
            )


def test_optimizer_initialization_and_solver_failures_are_wrapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    estimates = _estimate(_returns(), OptimizationConfig())

    def broken_factory(*_args: object, **_kwargs: object) -> object:
        raise ValueError("solver internals")

    monkeypatch.setattr(
        optimization.importlib,
        "import_module",
        lambda _name: SimpleNamespace(EfficientFrontier=broken_factory),
    )
    with pytest.raises(OptimizationError, match="Unable to initialize") as error:
        _create_frontier(
            estimates,
            OptimizationConfig(),
            _Request("min_volatility"),
            (0.0, 1.0),
        )
    assert isinstance(error.value.__cause__, ValueError)

    class BrokenFrontier:
        def min_volatility(self) -> None:
            raise RuntimeError("solver internals")

    monkeypatch.setattr(
        optimization.importlib,
        "import_module",
        lambda _name: SimpleNamespace(
            EfficientFrontier=lambda *_args, **_kwargs: BrokenFrontier()
        ),
    )
    with pytest.raises(OptimizationError, match="failed while running"):
        optimization.min_volatility(_returns())


def test_optimizer_requires_volatility_target() -> None:
    with pytest.raises(ValueError, match="target_volatility"):
        _run_objective(
            _DummyFrontier(), _Request("efficient_risk"), OptimizationConfig()
        )


def test_optimizer_requires_return_target() -> None:
    with pytest.raises(ValueError, match="target_return"):
        _run_objective(
            _DummyFrontier(), _Request("efficient_return"), OptimizationConfig()
        )


def test_optimizer_rejects_unknown_objective() -> None:
    with pytest.raises(ValueError, match="Unknown optimization method"):
        _run_objective(_DummyFrontier(), _Request("unknown"), OptimizationConfig())


def test_hrp_handles_single_asset_zero_variance_and_library_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    single = pd.DataFrame({"only": [-0.1, 0.1, -0.05]})
    assert _hrp_weights(single).iloc[0] == pytest.approx(1.0)
    with pytest.raises(ValueError, match="positive asset variances"):
        _hrp_weights(pd.DataFrame({"constant": [0.0, 0.0]}))

    class FakeHRP:
        weights = np.array([0.6, 0.4])

        def optimize(self) -> None:
            return None

    monkeypatch.setattr(optimization.hierarchy, "_LINKAGE_METHODS", {}, raising=False)
    monkeypatch.setattr(
        optimization.importlib,
        "import_module",
        lambda _name: SimpleNamespace(HRPOpt=lambda **_kwargs: FakeHRP()),
    )
    result = optimize_hrp(_returns())

    assert result.assumptions["implementation"] == "PyPortfolioOpt"
    assert result.weights.to_list() == pytest.approx([0.6, 0.4])


def test_hrp_wraps_backend_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_factory(**_kwargs: object) -> object:
        raise RuntimeError("private backend details")

    monkeypatch.setattr(
        optimization.importlib,
        "import_module",
        lambda _name: SimpleNamespace(HRPOpt=broken_factory),
    )

    with pytest.raises(OptimizationError, match="failed while running HRP"):
        optimize_hrp(_returns())


def test_black_litterman_wraps_model_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    estimates = _estimate(_returns(), OptimizationConfig())
    request = _BLRequest(
        prior=pd.Series({"a": 0.04, "b": 0.03}),
        view_kwargs={"absolute_views": {"a": 0.05}},
        view_type="absolute",
        tau=0.05,
        market_caps=None,
    )

    def broken_model(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("private model details")

    monkeypatch.setattr(
        optimization.importlib,
        "import_module",
        lambda _name: SimpleNamespace(BlackLittermanModel=broken_model),
    )
    with pytest.raises(OptimizationError, match="failed while running Black-Litterman"):
        _run_black_litterman(estimates, OptimizationConfig(), request)
