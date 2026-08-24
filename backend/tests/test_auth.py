from fastapi.testclient import TestClient


def test_registration_session_csrf_and_logout(client: TestClient) -> None:
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "password": "correct horse battery staple",
            "display_name": "Test Driver",
        },
    )
    assert registered.status_code == 201
    assert registered.json()["user"]["email"] == "test@example.com"
    assert "vehinode_session" in client.cookies

    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.post("/api/v1/auth/logout").status_code == 403

    csrf = registered.json()["csrf_token"]
    assert client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_request_id_security_headers_and_payload_limit(client: TestClient) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "test-request-123"})
    assert response.headers["X-Request-ID"] == "test-request-123"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "geolocation=()" in response.headers["Permissions-Policy"]
    generated = client.get("/health/live", headers={"X-Request-ID": "invalid request id"})
    assert generated.headers["X-Request-ID"] != "invalid request id"
    oversized = client.post(
        "/api/v1/auth/login",
        content=b"x" * 2_000_001,
        headers={"Content-Type": "application/json"},
    )
    assert oversized.status_code == 413
    assert oversized.json()["error"]["code"] == "payload_too_large"


def test_local_identity_and_device_auth_realms_are_isolated(
    registered: tuple[TestClient, str],
) -> None:
    client, csrf = registered
    vehicle = client.post(
        "/api/v1/vehicles",
        headers={"X-CSRF-Token": csrf},
        json={"name": "C-Zero", "manufacturer": "Citroën", "model": "C-Zero"},
    ).json()
    enrollment = client.post(
        f"/api/v1/vehicles/{vehicle['id']}/enrollments",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Tracker"},
    ).json()
    enrolled = client.post(
        "/api/v1/device/enroll",
        json={
            "token": enrollment["token"],
            "agent_version": "test",
            "hostname": "simulator",
        },
    ).json()

    device_header = {"Authorization": f"Device {enrolled['credential']}"}
    client.cookies.clear()
    assert client.get("/api/v1/auth/me", headers=device_header).status_code == 401
    assert client.get("/api/v1/device/config").status_code == 401
    assert client.get("/api/v1/device/config", headers=device_header).status_code == 200


def test_active_session_revocation_and_password_change(client: TestClient) -> None:
    first = client.post(
        "/api/v1/auth/register",
        json={
            "email": "sessions@example.com",
            "password": "initial-password-value",
            "display_name": "Session Owner",
        },
    )
    assert first.status_code == 201
    first_id = client.get("/api/v1/auth/sessions").json()[0]["id"]

    second = client.post(
        "/api/v1/auth/login",
        json={"email": "sessions@example.com", "password": "initial-password-value"},
    )
    csrf = second.json()["csrf_token"]
    sessions = client.get("/api/v1/auth/sessions").json()
    assert len(sessions) == 2
    assert sum(row["current"] for row in sessions) == 1
    revoked = client.delete(f"/api/v1/auth/sessions/{first_id}", headers={"X-CSRF-Token": csrf})
    assert revoked.status_code == 204
    assert len(client.get("/api/v1/auth/sessions").json()) == 1

    changed = client.post(
        "/api/v1/auth/password",
        headers={"X-CSRF-Token": csrf},
        json={
            "current_password": "initial-password-value",
            "new_password": "replacement-password-value",
        },
    )
    assert changed.status_code == 204
    assert client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "sessions@example.com", "password": "initial-password-value"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "sessions@example.com", "password": "replacement-password-value"},
        ).status_code
        == 200
    )
