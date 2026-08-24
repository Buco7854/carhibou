import json
import ssl
from collections.abc import Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID

from agent.vehicle_agent import __version__
from agent.vehicle_agent.models import Sample
from agent.vehicle_agent.server_url import validate_server_url


class TransportError(Exception):
    pass


class HTTPSBatchTransport:
    def __init__(self, server_url: str, credential: str, boot_id: str, timeout: float = 20):
        server_url = validate_server_url(server_url)
        UUID(boot_id)
        self.endpoint = server_url + "/api/v1/device/telemetry/batch"
        self.config_endpoint = server_url + "/api/v1/device/config"
        self.credential = credential
        self.boot_id = boot_id
        self.timeout = timeout

    def upload(self, samples: Sequence[Sample]) -> list[str]:
        body = json.dumps(
            {"boot_id": self.boot_id, "samples": [sample.as_payload() for sample in samples]}
        ).encode()
        request = Request(
            self.endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Device {self.credential}",
                "Content-Type": "application/json",
                "User-Agent": f"VehiNode-Agent/{__version__}",
            },
        )
        try:
            with urlopen(  # noqa: S310 - URL scheme is validated above
                request, timeout=self.timeout, context=ssl.create_default_context()
            ) as response:
                payload = json.load(response)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise TransportError(f"telemetry upload failed: {exc}") from exc
        accepted = payload.get("accepted", [])
        duplicates = payload.get("duplicates", [])
        return [str(value) for value in (*accepted, *duplicates)]

    def fetch_config(self) -> dict[str, object]:
        request = Request(
            self.config_endpoint,
            method="GET",
            headers={
                "Authorization": f"Device {self.credential}",
                "User-Agent": f"VehiNode-Agent/{__version__}",
            },
        )
        try:
            with urlopen(  # noqa: S310 - URL scheme is validated in the constructor
                request, timeout=self.timeout, context=ssl.create_default_context()
            ) as response:
                payload = json.load(response)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise TransportError(f"configuration sync failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise TransportError("configuration response is not an object")
        return payload
