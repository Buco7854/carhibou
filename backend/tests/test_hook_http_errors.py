"""A hook that cannot reach a server should be told so in one line.

A user pointed a Traccar hook at a non-HTTP protocol port and read sixty lines of
httpx and httpcore frames to discover that nothing had answered.
"""

from contextlib import contextmanager

import httpx
import pytest

from backend.app.hooks.context import MAX_HTTP_RESPONSE_BYTES, HookHTTP, HookHTTPError

# A path and a query that must never reach the message: the identifier locates a
# record and the token authenticates to it.
URL = "http://tracker.example.com:5013/api/positions?token=s3cr3t-value&id=42"


def _failing(error: Exception) -> httpx.MockTransport:
    def raise_it(_request: httpx.Request) -> httpx.Response:
        raise error

    return httpx.MockTransport(raise_it)


def _request(monkeypatch: pytest.MonkeyPatch, error: Exception, url: str = URL) -> HookHTTPError:
    @contextmanager
    def scripted(*args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        del args, kwargs
        with (
            httpx.Client(transport=_failing(error)) as client,
            client.stream("GET", url) as response,
        ):
            yield response

    monkeypatch.setattr(httpx, "stream", scripted)
    with pytest.raises(HookHTTPError) as raised:
        HookHTTP().get(url, timeout=8)
    return raised.value


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError("All connection attempts failed"),
        httpx.ReadError("Connection broken"),
        httpx.WriteError("Broken pipe"),
        httpx.RemoteProtocolError("Server disconnected without sending a response."),
        httpx.LocalProtocolError("Illegal header value"),
        httpx.ProxyError("Proxy refused"),
        httpx.CloseError("Close failed"),
    ],
)
def test_every_transport_failure_becomes_one_readable_line(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    failure = _request(monkeypatch, error)
    message = str(failure)

    assert "\n" not in message
    assert message.startswith("GET http://tracker.example.com:5013")
    # The original stays reachable for the traceback tail.
    assert failure.__cause__ is error


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectTimeout("timed out"),
        httpx.ReadTimeout("timed out"),
        httpx.WriteTimeout("timed out"),
        httpx.PoolTimeout("timed out"),
    ],
)
def test_timeouts_say_how_long_they_waited(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    message = str(_request(monkeypatch, error))
    assert message == "GET http://tracker.example.com:5013 timed out after 8s"


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError("All connection attempts failed"),
        httpx.RemoteProtocolError("Server disconnected without sending a response."),
        httpx.ConnectTimeout("timed out"),
        httpx.ProxyError("Proxy refused"),
    ],
)
def test_the_message_never_carries_the_path_query_or_credentials(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    """A URL is not a safe thing to quote back: the query carries the token."""
    message = str(_request(monkeypatch, error))
    for secret in ("s3cr3t-value", "token", "positions", "id=42", "?"):
        assert secret not in message, f"{secret!r} leaked into {message!r}"


def test_credentials_in_the_url_are_not_quoted_back(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "https://admin:hunter2@tracker.example.com:8443/feed?key=abc"
    message = str(_request(monkeypatch, httpx.ConnectError("refused"), url=url))
    assert message.startswith("GET https://tracker.example.com:8443 failed:")
    assert "hunter2" not in message and "admin" not in message and "abc" not in message


def test_a_bare_disconnect_says_the_port_may_not_speak_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reported case: a Traccar device port accepts the connection and then
    closes it, which reads as an outage but is a wrong port number."""
    failure = _request(
        monkeypatch, httpx.RemoteProtocolError("Server disconnected without sending a response.")
    )
    assert str(failure) == (
        "GET http://tracker.example.com:5013 failed: "
        "server disconnected without sending a response - "
        "this port may not speak HTTP (Traccar's OsmAnd HTTP port is 5055 by default)"
    )


def test_other_failures_do_not_get_the_port_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    message = str(_request(monkeypatch, httpx.ConnectError("All connection attempts failed")))
    assert message == ("GET http://tracker.example.com:5013 failed: all connection attempts failed")
    assert "speak HTTP" not in message


def test_a_default_port_is_named_without_inventing_one(monkeypatch: pytest.MonkeyPatch) -> None:
    message = str(
        _request(monkeypatch, httpx.ConnectError("refused"), url="https://example.com/a?b=c")
    )
    assert message == "GET https://example.com failed: refused"


def test_responses_still_come_back_when_the_transport_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wrapper must not swallow the ordinary path."""

    @contextmanager
    def scripted(*args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        del args, kwargs
        transport = httpx.MockTransport(lambda _r: httpx.Response(204, text="fine"))
        with httpx.Client(transport=transport) as client, client.stream("GET", URL) as response:
            yield response

    monkeypatch.setattr(httpx, "stream", scripted)
    response = HookHTTP().get(URL)
    assert response.status_code == 204
    assert response.text == "fine"


def test_an_oversized_response_fails_instead_of_returning_partial_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @contextmanager
    def scripted(*args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        del args, kwargs
        content = b"x" * (MAX_HTTP_RESPONSE_BYTES + 100_000)
        transport = httpx.MockTransport(lambda _r: httpx.Response(200, content=content))
        with httpx.Client(transport=transport) as client, client.stream("GET", URL) as response:
            yield response

    monkeypatch.setattr(httpx, "stream", scripted)
    with pytest.raises(HookHTTPError) as raised:
        HookHTTP().get(URL)
    assert str(raised.value) == "GET http://tracker.example.com:5013 response exceeded 1 MB"
