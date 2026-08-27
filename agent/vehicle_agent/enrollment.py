import json
import os
import ssl
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from agent.vehicle_agent import __version__
from agent.vehicle_agent.server_url import validate_server_url


class EnrollmentError(Exception):
    pass


def enroll(
    server_url: str, token: str, hostname: str, hardware: dict[str, object]
) -> dict[str, object]:
    try:
        server_url = validate_server_url(server_url)
    except ValueError as exc:
        raise EnrollmentError(str(exc)) from exc
    request = Request(
        server_url + "/api/v1/device/enroll",
        data=json.dumps(
            {
                "token": token,
                "implementation_id": "custom",
                "protocol_version": 1,
                "agent_version": __version__,
                "hostname": hostname,
                "hardware": hardware,
            }
        ).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(  # noqa: S310 - scheme is validated above
            request, timeout=30, context=ssl.create_default_context()
        ) as response:
            return dict(json.load(response))
    except (HTTPError, URLError, json.JSONDecodeError) as exc:
        raise EnrollmentError(f"device enrollment failed: {exc}") from exc


def store_credentials(path: str | Path, data: dict[str, object], server_url: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "server_url": validate_server_url(server_url),
        "device_id": data["device_id"],
        "vehicle_id": data["vehicle_id"],
        "credential": data["credential"],
    }
    with NamedTemporaryFile("w", dir=target.parent, delete=False) as temporary:
        json.dump(payload, temporary, indent=2)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    os.chmod(temporary_path, 0o600)
    temporary_path.replace(target)
