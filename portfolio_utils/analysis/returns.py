"""Calendar alignment and vectorized transformations from prices to returns."""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

from portfolio_utils.analysis._validation import validate_price_panel

_MIN_PRICE_COUNT = 2


def align_prices(
    prices: pd.DataFrame,
    *,
    policy: str,
    limit: int | None = None,
) -> pd.DataFrame:
    """Align price calendars without back-filling unavailable observations.

    ``inner`` retains dates observed for every asset. ``ffill`` carries only
    past observations forward and requires a maximum fill distance.

    :param prices: Wide price panel with possibly different asset calendars.
    :param policy: ``"inner"`` to intersect calendars or ``"ffill"`` to
        forward-fill at most ``limit`` rows.
    :param limit: Positive maximum number of forward-filled rows; required for
        ``policy="ffill"``.
    :raises ValueError: If the panel, policy, or fill limit is invalid.
    :return: Aligned panel with no missing observations.

    >>> import pandas as pd
    >>> dates = pd.date_range(
    ...     "2024-01-01",
    ...     periods=3,
    ...     freq="D",
    ... )
    >>> prices = pd.DataFrame(
    ...     {
    ...         "a": [
    ...             1.0,
    ...             2.0,
    ...             3.0,
    ...         ],
    ...         "b": [
    ...             4.0,
    ...             float(
    ...                 "nan"
    ...             ),
    ...             6.0,
    ...         ],
    ...     },
    ...     index=dates,
    ... )
    >>> align_prices(
    ...     prices,
    ...     policy="inner",
    ... ).shape
    (2, 2)
    """
    validate_price_panel(prices)
    if policy not in {"inner", "ffill"}:
        raise ValueError(
            "policy must be 'inner' or 'ffill'; back-filling is not allowed."
        )
    if policy == "inner":
        if limit is not None:
            raise ValueError("limit is only valid when policy='ffill'.")
        aligned = prices.dropna(axis=0, how="any")
    else:
        if limit is None or limit < 1:
            raise ValueError("A positive limit is required when policy='ffill'.")
        aligned = prices.ffill(limit=limit).dropna(axis=0, how="any")
    if aligned.empty:
        raise ValueError("Calendar alignment leaves no complete price observations.")
    return aligned.astype(float)


def prices_to_returns(
    prices: pd.DataFrame,
    *,
    method: Literal["simple", "log"] = "simple",
    alignment_policy: str = "inner",
    ffill_limit: int | None = None,
) -> pd.DataFrame:
    """Calculate simple or log returns after explicit calendar alignment.

    Simple returns are appropriate for aggregation across assets; log returns
    are additive through time. The first undefined return is removed
    explicitly. No backward filling is performed.

    :param prices: Wide close-price panel.
    :param method: Return convention, either ``"simple"`` or ``"log"``.
    :param alignment_policy: Calendar policy passed to :func:`align_prices`.
    :param ffill_limit: Maximum forward-fill distance when using ``"ffill"``.
    :raises ValueError: If prices or options are invalid, or fewer than two
        aligned prices remain.
    :return: Wide return panel with its first undefined row removed.

    >>> import pandas as pd
    >>> prices = pd.DataFrame(
    ...     {
    ...         "a": [
    ...             100.0,
    ...             110.0,
    ...             99.0,
    ...         ]
    ...     },
    ...     index=pd.date_range(
    ...         "2024-01-01",
    ...         periods=3,
    ...         freq="D",
    ...     ),
    ... )
    >>> prices_to_returns(
    ...     prices
    ... )["a"].round(
    ...     2
    ... ).tolist()
    [0.1, -0.1]
    """
    if method not in {"simple", "log"}:
        raise ValueError("method must be 'simple' or 'log'.")
    aligned = align_prices(prices, policy=alignment_policy, limit=ffill_limit)
    if len(aligned) < _MIN_PRICE_COUNT:
        raise ValueError(
            "At least two aligned prices are required to calculate returns."
        )
    if method == "simple":
        result = aligned.pct_change(fill_method=None)
    else:
        logged: pd.DataFrame = aligned.apply(np.log)
        result = logged.diff()
    returns = result.iloc[1:].astype(float)
    if returns.empty or not np.isfinite(returns.to_numpy(dtype=float)).all():
        raise ValueError("Calculated returns must be finite and non-empty.")
    return returns
