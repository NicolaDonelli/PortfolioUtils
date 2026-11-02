"""Tests for the throttled HTTP client."""

from collections.abc import Mapping, Sequence

import pytest
from curl_cffi import requests

from portfolio_utils.download.client import InvestingHttpClient
from portfolio_utils.download.errors import (
    BlockedResponseError,
    DownloadError,
    RateLimitedError,
    UnexpectedResponseError,
)


class FakeResponse:
    """Minimal HTTP response fake."""

    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self.payload = payload
        self.text = payload if isinstance(payload, str) else ""

    def json(self) -> object:
        """Return the configured payload."""
        return self.payload


class InvalidJsonResponse(FakeResponse):
    """Response fake that fails JSON decoding."""

    def json(self) -> object:
        """Raise the same base exception used for malformed JSON."""
        raise ValueError("private response body")


class FakeSession:
    """Session fake recording requests."""

    def __init__(
        self,
        responses: Sequence[FakeResponse | requests.exceptions.RequestException],
    ) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, Mapping[str, str] | None]] = []

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, str] | None,
        headers: Mapping[str, str] | None,
        timeout: float,
    ) -> FakeResponse:
        """Return a recorded response."""
        _ = headers, timeout
        self.calls.append((url, params))
        response = self.responses.pop(0)
        if isinstance(response, requests.exceptions.RequestException):
            raise response
        return response


def test_http_client_spaces_sequential_requests() -> None:
    """Requests begin at least the configured interval apart."""
    now = [0.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    session = FakeSession([FakeResponse(200, {"ok": True}) for _ in range(2)])
    client = InvestingHttpClient(
        session=session,
        min_interval_s=1.5,
        clock=lambda: now[0],
        sleep=sleep,
    )

    client.get_json("https://example.test/one")
    client.get_json("https://example.test/two")

    assert sleeps == [pytest.approx(1.5)]
    assert len(session.calls) == 2


@pytest.mark.parametrize(
    ("status_code", "exception"),
    [
        (403, BlockedResponseError),
    ],
)
def test_http_client_rejects_blocked_limited_and_invalid_payloads(
    status_code: int,
    exception: type[Exception],
) -> None:
    """Non-usable responses raise explicit safe errors."""
    payload: object = {"some": "json"}
    client = InvestingHttpClient(
        session=FakeSession([FakeResponse(status_code, payload)])
    )

    with pytest.raises(exception):
        client.get_json("https://example.test/data")


def test_http_client_retries_rate_limit_with_backoff() -> None:
    """HTTP 429 is retried and then raised explicitly if it persists."""
    now = [0.0]
    delays: list[float] = []

    def sleep(seconds: float) -> None:
        delays.append(seconds)
        now[0] += seconds

    session = FakeSession([FakeResponse(429, {}) for _ in range(4)])
    client = InvestingHttpClient(
        session=session,
        clock=lambda: now[0],
        sleep=sleep,
    )

    with pytest.raises(RateLimitedError):
        client.get_json("https://example.test/data")

    assert len(session.calls) == 4
    assert len(delays) >= 3
    assert sum(delays) >= 7.5


def test_http_client_retries_server_errors() -> None:
    """HTTP 5xx responses retry and may then succeed."""
    session = FakeSession([FakeResponse(503, {}), FakeResponse(200, {"ok": True})])
    now = [0.0]

    def sleep(seconds: float) -> None:
        now[0] += seconds

    client = InvestingHttpClient(
        session=session,
        clock=lambda: now[0],
        sleep=sleep,
    )

    assert client.get_json("https://example.test/data") == {"ok": True}
    assert len(session.calls) == 2


def test_http_client_retries_connection_errors() -> None:
    """Transient connection failures use the same bounded backoff as HTTP errors."""
    session = FakeSession(
        [
            requests.exceptions.ConnectionError("temporary failure"),
            FakeResponse(200, {"ok": True}),
        ]
    )
    now = [0.0]

    def sleep(seconds: float) -> None:
        now[0] += seconds

    client = InvestingHttpClient(
        session=session,
        clock=lambda: now[0],
        sleep=sleep,
    )

    assert client.get_json("https://example.test/data") == {"ok": True}
    assert len(session.calls) == 2


def test_http_client_does_not_retry_other_client_errors() -> None:
    """HTTP 4xx responses other than 429 fail immediately."""
    session = FakeSession([FakeResponse(404, {}), FakeResponse(200, {})])
    client = InvestingHttpClient(session=session, sleep=lambda _seconds: None)

    with pytest.raises(DownloadError, match="404"):
        client.get_json("https://example.test/data")

    assert len(session.calls) == 1


def test_http_client_reports_invalid_json_without_echoing_body() -> None:
    """Malformed response bodies have a safe explicit error."""
    client = InvestingHttpClient(session=FakeSession([InvalidJsonResponse(200, None)]))

    with pytest.raises(UnexpectedResponseError, match="valid JSON") as error:
        client.get_json("https://example.test/data")

    assert "private response body" not in str(error.value)


def test_http_client_does_not_expose_response_body_in_errors() -> None:
    """Unexpected response messages omit potentially sensitive response data."""
    client = InvestingHttpClient(
        session=FakeSession(
            [FakeResponse(503, {"token": "private-value"}) for _ in range(4)]
        )
    )

    with pytest.raises(DownloadError) as error:
        client.get_json("https://example.test/data")

    assert "private-value" not in str(error.value)


@pytest.mark.parametrize(
    ("minimum_interval", "timeout", "message"),
    [
        (1.0, 30.0, "at least 1.5"),
        (1.5, 0.0, "timeout_s must be positive"),
    ],
)
def test_http_client_rejects_invalid_timing_configuration(
    minimum_interval: float, timeout: float, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        InvestingHttpClient(
            session=FakeSession([]),
            min_interval_s=minimum_interval,
            timeout_s=timeout,
        )


def test_http_client_returns_text_and_maps_text_status_errors() -> None:
    client = InvestingHttpClient(
        session=FakeSession([FakeResponse(200, "plain response")])
    )
    assert client.get_text("https://example.test/page") == "plain response"

    for responses, exception in (
        ([FakeResponse(403, "private response")], BlockedResponseError),
        ([FakeResponse(429, "private response") for _ in range(4)], RateLimitedError),
        ([FakeResponse(404, "private response")], DownloadError),
    ):
        with pytest.raises(exception):
            InvestingHttpClient(
                session=FakeSession(responses),
                sleep=lambda _seconds: None,
            ).get_text("https://example.test/page")


def test_http_client_exhausted_connection_retries_omit_exception_details() -> None:
    session = FakeSession(
        [
            requests.exceptions.ConnectionError("private connection detail")
            for _ in range(4)
        ]
    )
    now = [0.0]
    client = InvestingHttpClient(
        session=session,
        sleep=lambda seconds: now.__setitem__(0, now[0] + seconds),
        clock=lambda: now[0],
    )

    with pytest.raises(DownloadError, match="failed after retries") as error:
        client.get_json("https://example.test/data")

    assert "private connection detail" not in str(error.value)
    assert len(session.calls) == 4
