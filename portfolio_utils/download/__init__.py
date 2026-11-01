"""Public facade for sequential Investing.com ETF historical downloads.

The public HTML and historical endpoint are implemented from the verified evidence
documented in :mod:`portfolio_utils.download.source`. Catalog enumeration follows
categories linked by the index and explicit pagination links; completeness beyond
those observed pages is not claimed.
"""

from portfolio_utils.download.downloader import download_etfs
from portfolio_utils.download.errors import (
    BlockedResponseError,
    DownloadError,
    EndpointUnavailableError,
    InstrumentNotFoundError,
    NoHistoryError,
    RateLimitedError,
    UnexpectedResponseError,
)
from portfolio_utils.download.models import Instrument, PriceRow
from portfolio_utils.download.source import InvestingComSource, InvestingDataSource

__all__ = [
    "BlockedResponseError",
    "DownloadError",
    "EndpointUnavailableError",
    "Instrument",
    "InstrumentNotFoundError",
    "InvestingComSource",
    "InvestingDataSource",
    "NoHistoryError",
    "PriceRow",
    "RateLimitedError",
    "UnexpectedResponseError",
    "download_etfs",
]
