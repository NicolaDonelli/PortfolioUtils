"""Opt-in live checks against Investing.com's public ETF pages and data."""

from datetime import date

from portfolio_utils.download import InvestingComSource


def test_public_catalog_and_historical_prices() -> None:
    """Fetch the public ETF catalog and a known ETF's historical prices."""
    source = InvestingComSource(min_interval_s=2.0)
    instruments = source.list_etfs()

    spy = next(
        (
            instrument
            for instrument in instruments
            if instrument.symbol.upper() == "SPY"
        ),
        None,
    )
    assert spy is not None, "SPY was not found in the public ETF catalog."

    rows = source.history(spy, date(2025, 1, 2), date(2025, 1, 10))

    assert rows
    assert all(date(2025, 1, 2) <= row.date <= date(2025, 1, 10) for row in rows)
    assert all(row.close > 0 for row in rows)
