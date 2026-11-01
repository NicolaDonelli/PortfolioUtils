"""Errors raised by investing.com download utilities."""


class DownloadError(RuntimeError):
    """Base error for download failures."""


class EndpointUnavailableError(DownloadError):
    """Raised when the requested data source is not available."""


class BlockedResponseError(DownloadError):
    """Raised when a request is blocked by the remote service."""


class RateLimitedError(DownloadError):
    """Raised when the remote service reports a rate limit."""


class InstrumentNotFoundError(DownloadError):
    """Raised when an identifier cannot be resolved."""


class UnexpectedResponseError(DownloadError):
    """Raised when a response or price record is invalid."""


class NoHistoryError(UnexpectedResponseError):
    """Raised when a valid instrument has no historical price rows."""
