import base64
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2ZQAAAABJRU5ErkJggg=="
)


def _profile(name: str) -> dict[str, object]:
    return {
        "name": name,
        "description": "Permission model fixture",
        "signals": [
            {
                "name": "battery.soc",
                "display_name": "Battery level",
                "source": {"type": "can", "can_id": 0x374},
                "decoder": {"byte_offset": 1, "data_type": "uint8", "scale": 0.5},
                "unit": "%",
                "minimum": 0,
                "maximum": 100,
            }
        ],
        "computed_metrics": [],
    }


def _login(app: Any, email: str) -> tuple[TestClient, str]:
    session = TestClient(app)
    response = session.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "permission-test-password"},
    )
    assert response.status_code == 200, response.text
    return session, response.json()["csrf_token"]


def _request(
    session: TestClient,
    csrf: str,
    method: str,
    url: str,
    json: object = None,
    content: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    merged = {"X-CSRF-Token": csrf, **(headers or {})}
    response: httpx.Response = session.request(
        method, url, headers=merged, json=json, content=content
    )
    return response


def test_four_personas_enforce_the_complete_access_model(
    registered: tuple[TestClient, str],
) -> None:
    admin, admin_csrf = registered
    admin_headers = {"X-CSRF-Token": admin_csrf}

    v1_response = admin.post("/api/v1/vehicles", headers=admin_headers, json={"name": "V1"})
    v2_response = admin.post("/api/v1/vehicles", headers=admin_headers, json={"name": "V2"})
    assert v1_response.status_code == v2_response.status_code == 201
    v1, v2 = v1_response.json(), v2_response.json()
    assert v1["access"] == v2["access"] == "operate"

    users: dict[str, dict[str, object]] = {}
    for persona, can_create_profiles in (
        ("operator", False),
        ("viewer", False),
        ("stranger", False),
        ("editor", True),
    ):
        created = admin.post(
            "/api/v1/users",
            headers=admin_headers,
            json={
                "email": f"{persona}@example.com",
                "display_name": persona.title(),
                "password": "permission-test-password",
                "can_create_profiles": can_create_profiles,
            },
        )
        assert created.status_code == 201, created.text
        users[persona] = created.json()
        assert created.json()["can_create_profiles"] is can_create_profiles

    grants = admin.put(
        f"/api/v1/vehicles/{v1['id']}/access",
        headers=admin_headers,
        json=[
            {"user_id": users["operator"]["id"], "level": "operate"},
            {"user_id": users["viewer"]["id"], "level": "view"},
        ],
    )
    assert grants.status_code == 200, grants.text
    assert grants.json() == [
        {
            "user_id": users["operator"]["id"],
            "email": "operator@example.com",
            "display_name": "Operator",
            "level": "operate",
        },
        {
            "user_id": users["viewer"]["id"],
            "email": "viewer@example.com",
            "display_name": "Viewer",
            "level": "view",
        },
    ]

    sessions = {
        "admin": (admin, admin_csrf),
        **{name: _login(admin.app, f"{name}@example.com") for name in users},
    }

    expected = {
        "admin": {v1["id"], v2["id"]},
        "operator": {v1["id"]},
        "viewer": {v1["id"]},
        "stranger": set(),
        "editor": set(),
    }
    for persona, (session, _csrf) in sessions.items():
        listed = session.get("/api/v1/vehicles")
        assert listed.status_code == 200
        assert {row["id"] for row in listed.json()} == expected[persona]
        assert all(
            row["access"] == ("operate" if persona in {"admin", "operator"} else "view")
            for row in listed.json()
        )

    for persona in ("operator", "viewer", "stranger"):
        session, _csrf = sessions[persona]
        assert session.get(f"/api/v1/vehicles/{v2['id']}").status_code == 404
        assert session.get(f"/api/v1/vehicles/{v2['id']}/history").status_code == 404
        assert session.get(f"/api/v1/vehicles/{v2['id']}/history/entries").status_code == 404

    enrollment = admin.post(
        f"/api/v1/vehicles/{v1['id']}/enrollments",
        headers=admin_headers,
        json={"name": "V1 agent"},
    )
    assert enrollment.status_code == 201, enrollment.text
    enrolled = admin.post(
        "/api/v1/device/enroll",
        json={
            "token": enrollment.json()["token"],
            "agent_version": "test",
            "hostname": "pi",
        },
    )
    assert enrolled.status_code == 201, enrolled.text
    device_id = enrolled.json()["device_id"]
    device_headers = {"Authorization": f"Device {enrolled.json()['credential']}"}
    batch = {
        "boot_id": str(uuid4()),
        "samples": [
            {
                "id": str(uuid4()),
                "sequence": 1,
                "recorded_at": datetime.now(UTC).isoformat(),
                "metrics": {"battery.soc": 50},
            }
        ],
    }
    assert admin.get("/api/v1/device/config", headers=device_headers).status_code == 200
    assert (
        admin.post("/api/v1/device/telemetry/batch", headers=device_headers, json=batch).status_code
        == 200
    )

    for persona in ("admin", "operator", "viewer", "stranger"):
        session, _csrf = sessions[persona]
        visible_devices = session.get("/api/v1/devices")
        assert visible_devices.status_code == 200
        assert {row["id"] for row in visible_devices.json()} == (
            {device_id} if persona in {"admin", "operator", "viewer"} else set()
        )

    mutation_cases = [
        ("delete", f"/api/v1/vehicles/{v1['id']}/telemetry", None),
        ("put", f"/api/v1/vehicles/{v1['id']}/profile", {"profile_id": None}),
        (
            "put",
            f"/api/v1/devices/{device_id}",
            {
                "name": "V1 agent",
                "sampling_seconds": 5,
                "upload_seconds": 5,
                "parked_sampling_seconds": 300,
                "parked_upload_seconds": 300,
            },
        ),
    ]
    for method, url, payload in mutation_cases:
        for persona, allowed_status in (
            ("admin", {200, 204}),
            ("operator", {200, 204}),
            ("viewer", {403}),
            ("stranger", {404}),
        ):
            session, csrf = sessions[persona]
            response = _request(session, csrf, method, url, json=payload)
            assert response.status_code in allowed_status, (persona, url, response.text)

    photo_url = f"/api/v1/vehicles/{v1['id']}/photo"
    for persona, expected_status in (
        ("admin", 204),
        ("operator", 204),
        ("viewer", 403),
        ("stranger", 404),
    ):
        session, csrf = sessions[persona]
        uploaded = _request(
            session,
            csrf,
            "put",
            photo_url,
            content=PNG,
            headers={"Content-Type": "image/png"},
        )
        assert uploaded.status_code == expected_status, (persona, uploaded.text)
    assert sessions["viewer"][0].get(photo_url).status_code == 200
    assert sessions["stranger"][0].get(photo_url).status_code == 404
    assert (
        _request(sessions["operator"][0], sessions["operator"][1], "delete", photo_url).status_code
        == 204
    )

    # Enrollment and every agent mutation are operate-only even though viewers can
    # see the agent in their list.
    for suffix, method in (("revoke", "post"), ("rotate", "post")):
        for persona, expected_status in (("viewer", 403), ("stranger", 404)):
            session, csrf = sessions[persona]
            assert (
                _request(session, csrf, method, f"/api/v1/devices/{device_id}/{suffix}").status_code
                == expected_status
            )
    for persona, expected_status in (("viewer", 403), ("stranger", 404)):
        session, csrf = sessions[persona]
        assert (
            _request(
                session,
                csrf,
                "post",
                f"/api/v1/vehicles/{v1['id']}/enrollments",
                json={"name": "Denied"},
            ).status_code
            == expected_status
        )
    operator, operator_csrf = sessions["operator"]
    operator_enrollment = _request(
        operator,
        operator_csrf,
        "post",
        f"/api/v1/vehicles/{v1['id']}/enrollments",
        json={"name": "Second V1 agent"},
    )
    assert operator_enrollment.status_code == 201
    second_device = admin.post(
        "/api/v1/device/enroll",
        json={
            "token": operator_enrollment.json()["token"],
            "agent_version": "test",
            "hostname": "second-pi",
        },
    )
    assert second_device.status_code == 201
    assert (
        _request(operator, operator_csrf, "post", f"/api/v1/devices/{device_id}/rotate").status_code
        == 200
    )
    assert (
        admin.post(f"/api/v1/devices/{device_id}/rotate", headers=admin_headers).status_code == 200
    )
    assert (
        _request(operator, operator_csrf, "post", f"/api/v1/devices/{device_id}/revoke").status_code
        == 204
    )
    assert (
        admin.post(f"/api/v1/devices/{device_id}/revoke", headers=admin_headers).status_code == 204
    )

    for persona in ("operator", "viewer", "stranger", "editor"):
        session, csrf = sessions[persona]
        assert (
            _request(session, csrf, "post", "/api/v1/vehicles", json={"name": "Denied"}).status_code
            == 403
        )
        assert _request(session, csrf, "delete", "/api/v1/vehicles/telemetry").status_code == 403
        assert _request(session, csrf, "delete", f"/api/v1/vehicles/{v1['id']}").status_code == (
            403 if persona in {"operator", "viewer"} else 404
        )

    admin_profile = admin.post(
        "/api/v1/vehicle-profiles", headers=admin_headers, json=_profile("Admin profile")
    )
    assert admin_profile.status_code == 201, admin_profile.text
    for persona in ("operator", "viewer", "stranger"):
        session, csrf = sessions[persona]
        assert (
            _request(
                session, csrf, "post", "/api/v1/vehicle-profiles", json=_profile("Denied")
            ).status_code
            == 403
        )
    editor, editor_csrf = sessions["editor"]
    own_profile = _request(
        editor, editor_csrf, "post", "/api/v1/vehicle-profiles", json=_profile("Editor profile")
    )
    assert own_profile.status_code == 201, own_profile.text
    assert own_profile.json()["editable"] is True
    assert all("editable" in row for row in editor.get("/api/v1/vehicle-profiles").json())
    assert (
        _request(
            editor,
            editor_csrf,
            "put",
            f"/api/v1/vehicle-profiles/{admin_profile.json()['id']}",
            json=_profile("Not mine"),
        ).status_code
        == 403
    )
    assert (
        admin.put(
            f"/api/v1/vehicles/{v1['id']}/profile",
            headers=admin_headers,
            json={"profile_id": own_profile.json()["id"]},
        ).status_code
        == 200
    )
    deleted_profile = _request(
        editor,
        editor_csrf,
        "delete",
        f"/api/v1/vehicle-profiles/{own_profile.json()['id']}",
    )
    assert deleted_profile.status_code == 204
    assert deleted_profile.content == b""
    assert admin.get(f"/api/v1/vehicles/{v1['id']}").json()["vehicle_profile"] is None

    hook = admin.post(
        "/api/v1/hooks",
        headers=admin_headers,
        json={"name": "Admin hook", "source": "pass"},
    )
    assert hook.status_code == 201, hook.text
    hook_id = hook.json()["id"]

    admin_only: list[tuple[str, str, object]] = [
        ("get", "/api/v1/hooks", None),
        ("post", "/api/v1/hooks", {"name": "Denied", "source": "pass"}),
        ("put", f"/api/v1/hooks/{hook_id}", {"name": "Denied", "source": "pass"}),
        ("delete", f"/api/v1/hooks/{hook_id}", None),
        ("get", f"/api/v1/hooks/{hook_id}/revisions", None),
        ("post", f"/api/v1/hooks/{hook_id}/revisions/1/restore", None),
        ("post", f"/api/v1/hooks/{hook_id}/test", {"telemetry_id": str(uuid4())}),
        ("get", f"/api/v1/hooks/{hook_id}/executions", None),
        ("post", f"/api/v1/hooks/executions/{uuid4()}/retry", None),
        ("get", "/api/v1/secrets", None),
        (
            "put",
            "/api/v1/secrets/token",
            {"name": "token", "value": "not-returned"},
        ),
        ("delete", "/api/v1/secrets/token", None),
        ("get", "/api/v1/users", None),
        ("get", "/api/v1/system/diagnostics", None),
        ("get", f"/api/v1/vehicles/{v1['id']}/access", None),
        ("put", f"/api/v1/vehicles/{v1['id']}/access", []),
        ("get", "/api/v1/admin/default-access", None),
        (
            "put",
            "/api/v1/admin/default-access",
            {"profiles_create": True, "grants": [{"vehicle_id": v2["id"], "level": "view"}]},
        ),
    ]
    for persona in ("operator", "viewer", "stranger", "editor"):
        session, csrf = sessions[persona]
        for method, url, body in admin_only:
            response = _request(session, csrf, method, url, json=body)
            assert response.status_code == 403, (persona, method, url, response.text)

    template = admin.put(
        "/api/v1/admin/default-access",
        headers=admin_headers,
        json={
            "profiles_create": True,
            "grants": [{"vehicle_id": v2["id"], "level": "view"}],
        },
    )
    assert template.status_code == 200
    assert template.json() == {
        "profiles_create": True,
        "grants": [{"vehicle_id": v2["id"], "level": "view"}],
    }
    future = admin.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": "future@example.com",
            "display_name": "Future",
            "password": "permission-test-password",
        },
    )
    assert future.status_code == 201, future.text
    assert future.json()["can_create_profiles"] is True
    future_session, _future_csrf = _login(admin.app, "future@example.com")
    assert {row["id"] for row in future_session.get("/api/v1/vehicles").json()} == {v2["id"]}

    # Changing the template never changes users who already exist.
    assert (
        admin.put(
            "/api/v1/admin/default-access",
            headers=admin_headers,
            json={"profiles_create": False, "grants": []},
        ).status_code
        == 200
    )
    assert {row["id"] for row in future_session.get("/api/v1/vehicles").json()} == {v2["id"]}

    assert (
        _request(operator, operator_csrf, "delete", f"/api/v1/devices/{device_id}").status_code
        == 204
    )
    assert (
        admin.delete(
            f"/api/v1/devices/{second_device.json()['device_id']}", headers=admin_headers
        ).status_code
        == 204
    )
    assert admin.delete(f"/api/v1/vehicles/{v2['id']}", headers=admin_headers).status_code == 204
