import base64
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from backend.app.auth.services import create_local_user
from backend.app.common.settings import get_settings
from backend.app.vehicles.models import VehiclePhoto
from backend.app.vehicles.photos import MAX_PHOTO_BYTES

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2ZQAAAABJRU5ErkJggg=="
)


@pytest.fixture
def media_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "media"
    monkeypatch.setattr(get_settings(), "media_dir", str(directory))
    return directory


def _create_vehicle(client: TestClient, csrf: str) -> dict[str, object]:
    response = client.post(
        "/api/v1/vehicles",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Photo car", "manufacturer": "Citroën", "model": "C-Zero"},
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, object], response.json())


def test_vehicle_photo_upload_cache_replace_and_delete(
    registered: tuple[TestClient, str], media_dir: Path, db_factory: sessionmaker[Session]
) -> None:
    client, csrf = registered
    vehicle = _create_vehicle(client, csrf)
    vehicle_id = vehicle["id"]
    photo_path = f"/api/v1/vehicles/{vehicle_id}/photo"

    missing_csrf = client.put(photo_path, content=PNG, headers={"Content-Type": "image/png"})
    assert missing_csrf.status_code == 403
    uploaded = client.put(
        photo_path,
        content=PNG,
        headers={"Content-Type": "image/png", "X-CSRF-Token": csrf},
    )
    assert uploaded.status_code == 204, uploaded.text
    stored_files = list(media_dir.rglob("*.png"))
    assert len(stored_files) == 1
    assert stored_files[0].read_bytes() == PNG
    with db_factory() as db:
        metadata = db.get(VehiclePhoto, vehicle_id)
        assert metadata is not None
        assert metadata.storage_key == stored_files[0].relative_to(media_dir).as_posix()
        assert not hasattr(metadata, "content")

    listed = client.get("/api/v1/vehicles").json()[0]
    assert listed["photo_url"].startswith(f"{photo_path}?v=")
    served = client.get(photo_path)
    assert served.status_code == 200
    assert served.content == PNG
    assert served.headers["content-type"] == "image/png"
    assert served.headers["cache-control"].startswith("private")
    etag = served.headers["etag"]
    assert client.get(photo_path, headers={"If-None-Match": etag}).status_code == 304

    replacement = PNG + b"replacement"
    assert (
        client.put(
            photo_path,
            content=replacement,
            headers={"Content-Type": "image/png", "X-CSRF-Token": csrf},
        ).status_code
        == 204
    )
    assert client.get(photo_path).content == replacement
    assert client.get("/api/v1/vehicles").json()[0]["photo_url"] != listed["photo_url"]
    assert len(list(media_dir.rglob("*.png"))) == 1

    removed = client.delete(photo_path, headers={"X-CSRF-Token": csrf})
    assert removed.status_code == 204
    assert client.get(photo_path).status_code == 404
    assert client.get("/api/v1/vehicles").json()[0]["photo_url"] is None
    assert not list(media_dir.rglob("*.png"))
    assert client.delete(photo_path, headers={"X-CSRF-Token": csrf}).status_code == 404


def test_vehicle_photo_validation_and_ownership(
    registered: tuple[TestClient, str],
    db_factory: sessionmaker[Session],
    media_dir: Path,
) -> None:
    assert MAX_PHOTO_BYTES == 25 * 1024 * 1024
    client, owner_csrf = registered
    vehicle = _create_vehicle(client, owner_csrf)
    photo_path = f"/api/v1/vehicles/{vehicle['id']}/photo"

    invalid_type = client.put(
        photo_path,
        content=b"<svg/>",
        headers={"Content-Type": "image/svg+xml", "X-CSRF-Token": owner_csrf},
    )
    assert invalid_type.status_code == 415
    mismatch = client.put(
        photo_path,
        content=b"not a png",
        headers={"Content-Type": "image/png", "X-CSRF-Token": owner_csrf},
    )
    assert mismatch.status_code == 415
    huge_dimensions = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        + (12_001).to_bytes(4, "big")
        + (100).to_bytes(4, "big")
    )
    rejected_dimensions = client.put(
        photo_path,
        content=huge_dimensions,
        headers={"Content-Type": "image/png", "X-CSRF-Token": owner_csrf},
    )
    assert rejected_dimensions.status_code == 415

    uploaded = client.put(
        photo_path,
        content=PNG,
        headers={"Content-Type": "image/png", "X-CSRF-Token": owner_csrf},
    )
    assert uploaded.status_code == 204
    with db_factory() as db:
        create_local_user(
            db,
            "photo-viewer@example.com",
            "photo-viewer-password",
            "Photo Viewer",
            admin=False,
        )
        db.commit()
    second_login = client.post(
        "/api/v1/auth/login",
        json={"email": "photo-viewer@example.com", "password": "photo-viewer-password"},
    )
    second_csrf = second_login.json()["csrf_token"]
    assert client.get(photo_path).status_code == 404
    assert (
        client.put(
            photo_path,
            content=PNG,
            headers={"Content-Type": "image/png", "X-CSRF-Token": second_csrf},
        ).status_code
        == 404
    )
    assert client.delete(photo_path, headers={"X-CSRF-Token": second_csrf}).status_code == 404


def test_vehicle_photo_upload_is_described_as_binary_in_openapi(client: TestClient) -> None:
    operation = client.get("/api/openapi.json").json()["paths"][
        "/api/v1/vehicles/{vehicle_id}/photo"
    ]["put"]
    content = operation["requestBody"]["content"]
    assert set(content) == {"image/jpeg", "image/png", "image/webp"}
    assert all(definition["schema"]["format"] == "binary" for definition in content.values())
