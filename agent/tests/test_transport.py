import io
import json
from datetime import UTC, datetime
from typing import Any, cast
from urllib.request import Request
from uuid import uuid4

import pytest

from agent.vehicle_agent.models import Sample
from agent.vehicle_agent.server_url import validate_server_url
from agent.vehicle_agent.transport import HTTPSBatchTransport


def test_batch_transport_preserves_ids_and_fetches_configuration(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    requests: list[Request] = []

    def fake_urlopen(request: Request, **_kwargs: Any) -> io.BytesIO:
        requests.append(request)
        if request.full_url.endswith("/config"):
            return io.BytesIO(
                json.dumps(
                    {
                        "version": 2,
                        "sampling": {"default_seconds": 10},
                        "upload": {"default_seconds": 60},
                        "vehicle_profile": "citroen-c-zero-v1",
                    }
                ).encode()
            )
        return io.BytesIO(json.dumps({"accepted": [sample.id], "duplicates": []}).encode())

    monkeypatch.setattr("agent.vehicle_agent.transport.urlopen", fake_urlopen)
    sample = Sample(sequence=1, recorded_at=datetime.now(UTC), position=None)
    transport = HTTPSBatchTransport("https://vehinode.example", "device-credential", str(uuid4()))
    assert transport.upload([sample]) == [sample.id]
    sent = json.loads(cast(bytes, requests[0].data or b"{}"))
    assert sent["samples"][0]["id"] == sample.id
    assert requests[0].get_header("Authorization") == "Device device-credential"
    assert transport.fetch_config()["version"] == 2
    assert requests[1].get_method() == "GET"


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost.evil.example",
        "http://127.0.0.1.evil.example",
        "https://user:password@example.com",
        "https://example.com/base-path",
        "ftp://example.com",
    ],
)
def test_server_url_rejects_non_https_and_ambiguous_origins(url: str) -> None:
    with pytest.raises(ValueError):
        validate_server_url(url)


def test_server_url_allows_https_and_exact_loopback() -> None:
    assert validate_server_url("https://cars.example/") == "https://cars.example"
    assert validate_server_url("http://localhost:8000") == "http://localhost:8000"
    assert validate_server_url("http://[::1]:8000") == "http://[::1]:8000"
