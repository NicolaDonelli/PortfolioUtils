"""Throttled HTTP primitives for the public Investing.com ETF adapter."""

import threading
import time
from collections.abc import Callable, Mapping
from secrets import randbelow
from typing import Protocol

from curl_cffi import requests

from portfolio_utils.download.errors import (
    BlockedResponseError,
    DownloadError,
    RateLimitedError,
    UnexpectedResponseError,
)

MINIMUM_REQUEST_INTERVAL_S = 1.5
HTTP_OK = 200
HTTP_FORBIDDEN = 403
HTTP_TOO_MANY_REQUESTS = 429
HTTP_SERVER_ERROR_MIN = 500
HTTP_SERVER_ERROR_MAX = 600
MAX_RETRIES = 3
MAX_JITTER_MS = 500


class HttpResponse(Protocol):
    """Minimal response API required by the HTTP client."""

    status_code: int
    text: str

    def json(self) -> object:
        """Decode the response body as JSON."""
        ...


class HttpSession(Protocol):
    """Minimal GET API required from a real or fake HTTP session."""

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, str] | None,
        headers: Mapping[str, str] | None,
        timeout: float,
    ) -> HttpResponse:
        """Perform one HTTP GET."""
        ...


class InvestingHttpClient:
    """A serial, minimum-interval HTTP client with safe response errors."""

    def __init__(
        self,
        session: HttpSession,
        min_interval_s: float = 1.5,
        timeout_s: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Initialize a client with an injected session and pacing controls.

        :param session: Injected HTTP session.
        :param min_interval_s: Minimum delay between request starts; at least 1.5s.
        :param timeout_s: Per-request timeout in seconds.
        :param sleep: Injectable sleep function.
        :param clock: Injectable monotonic clock.
        :raises ValueError: If the interval or timeout is invalid.
        """
        if min_interval_s < MINIMUM_REQUEST_INTERVAL_S:
            raise ValueError("min_interval_s must be at least 1.5 seconds.")
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive.")
        self._session = session
        self._min_interval_s = min_interval_s
        self._timeout_s = timeout_s
        self._sleep = sleep
        self._clock = clock
        self._last_request_at: float | None = None
        self._lock = threading.Lock()

    def get_json(
        self,
        url: str,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> object:
        """Perform one throttled GET and decode any valid JSON response.

        :param url: Full request URL.
        :param params: Optional query parameters.
        :param headers: Optional request headers.
        :raises BlockedResponseError: If the server responds with HTTP 403.
        :raises RateLimitedError: If the server responds with HTTP 429.
        :raises DownloadError: If the request fails or has another non-200 status.
        :raises UnexpectedResponseError: If the body is not valid JSON.
        :return: Decoded JSON value; endpoint-specific validation is not performed.
        """
        response = self._perform_with_retries(url, params, headers)
        if response.status_code == HTTP_FORBIDDEN:
            raise BlockedResponseError(
                "The service blocked the public request (HTTP 403)."
            )
        if response.status_code != HTTP_OK:
            if response.status_code == HTTP_TOO_MANY_REQUESTS:
                raise RateLimitedError(
                    "The service rate-limited the request (HTTP 429)."
                )
            raise DownloadError(
                f"The service returned unexpected HTTP status {response.status_code}."
            )
        try:
            return self._decode_json(response)
        except UnexpectedResponseError:
            raise

    def get_text(
        self,
        url: str,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> str:
        """Perform one throttled GET and return its text body.

        :param url: Full request URL.
        :param params: Optional query parameters.
        :param headers: Optional request headers.
        :raises BlockedResponseError: If the server responds with HTTP 403.
        :raises RateLimitedError: If the server responds with HTTP 429.
        :raises DownloadError: If the request has another non-200 status.
        :return: Response text.
        """
        response = self._perform_with_retries(url, params, headers)
        if response.status_code == HTTP_FORBIDDEN:
            raise BlockedResponseError(
                "The service blocked the public request (HTTP 403)."
            )
        if response.status_code == HTTP_TOO_MANY_REQUESTS:
            raise RateLimitedError("The service rate-limited the request (HTTP 429).")
        if response.status_code != HTTP_OK:
            raise DownloadError(
                f"The service returned unexpected HTTP status {response.status_code}."
            )
        return response.text

    def _perform_with_retries(
        self,
        url: str,
        params: Mapping[str, str] | None,
        headers: Mapping[str, str] | None,
    ) -> HttpResponse:
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self._perform_get(url, params, headers)
            except requests.exceptions.RequestException:
                if attempt == MAX_RETRIES:
                    raise DownloadError(
                        "The HTTP request failed after retries."
                    ) from None
                self._sleep(float(2**attempt) + randbelow(MAX_JITTER_MS) / 1000)
                continue
            retryable = response.status_code == HTTP_TOO_MANY_REQUESTS or (
                HTTP_SERVER_ERROR_MIN <= response.status_code < HTTP_SERVER_ERROR_MAX
            )
            if not retryable or attempt == MAX_RETRIES:
                return response
            self._sleep(float(2**attempt) + randbelow(MAX_JITTER_MS) / 1000)
        raise DownloadError("The HTTP request retry loop ended unexpectedly.")

    def _perform_get(
        self,
        url: str,
        params: Mapping[str, str] | None,
        headers: Mapping[str, str] | None,
    ) -> HttpResponse:
        with self._lock:
            now = self._clock()
            if self._last_request_at is not None:
                wait = self._min_interval_s - (now - self._last_request_at)
                if wait > 0:
                    self._sleep(wait)
            self._last_request_at = self._clock()
            return self._session.get(
                url,
                params=params,
                headers=headers,
                timeout=self._timeout_s,
            )

    @staticmethod
    def _decode_json(response: HttpResponse) -> object:
        try:
            payload = response.json()
        except ValueError:
            raise UnexpectedResponseError(
                "The response body was not valid JSON."
            ) from None
        return payload
