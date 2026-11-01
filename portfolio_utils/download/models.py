"""Typed models shared by downloader components."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Instrument:
    """Resolved exchange-traded fund descriptor."""

    investing_id: str
    name: str
    isin: str
    symbol: str
    exchange: str
    currency: str


@dataclass(frozen=True)
class PriceRow:
    """One daily OHLCV observation."""

    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int | None
