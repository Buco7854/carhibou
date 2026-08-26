import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.auth.models import AuthenticationIdentity
from backend.app.vehicles.models import Vehicle


def _create(client: TestClient, csrf: str, **overrides: object) -> httpx.Response:
    payload = {
        "email": "driver@example.com",
        "display_name": "Driver",
        "password": "another-long-password",
        "is_admin": False,
    }
    payload.update(overrides)
    response: httpx.Response = client.post(
        "/api/v1/users", headers={"X-CSRF-Token": csrf}, json=payload
    )
    return response


def test_administrator_creates_an_account_that_public_registration_still_refuses(
    registered: tuple[TestClient, str],
) -> None:
    client, csrf = registered
    created = _create(client, csrf)
    assert created.status_code == 201, created.text
    assert created.json()["email"] == "driver@example.com"
    assert created.json()["is_admin"] is False

    # The public endpoint stays closed; only an administrator may add identities.
    rejected = client.post(
        "/api/v1/auth/register",
        json={
            "email": "intruder@example.com",
            "password": "yet-another-long-password",
            "display_name": "Intruder",
        },
    )
    assert rejected.status_code == 403

    # The new account can sign in and is not an administrator.
    session = TestClient(client.app)
    login = session.post(
        "/api/v1/auth/login",
        json={"email": "driver@example.com", "password": "another-long-password"},
    )
    assert login.status_code == 200, login.text
    listing = session.get("/api/v1/users")
    assert listing.status_code == 403


def test_deactivated_account_cannot_sign_in(registered: tuple[TestClient, str]) -> None:
    client, csrf = registered
    user = _create(client, csrf).json()
    updated = client.patch(
        f"/api/v1/users/{user['id']}", headers={"X-CSRF-Token": csrf}, json={"is_active": False}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["is_active"] is False

    session = TestClient(client.app)
    refused = session.post(
        "/api/v1/auth/login",
        json={"email": "driver@example.com", "password": "another-long-password"},
    )
    assert refused.status_code == 401


def test_the_last_administrator_cannot_be_removed_or_demoted(
    registered: tuple[TestClient, str],
) -> None:
    client, csrf = registered
    owner = next(row for row in client.get("/api/v1/users").json() if row["is_admin"])

    # Nothing may leave the instance without a way back in.
    for payload in ({"is_admin": False}, {"is_active": False}):
        response = client.patch(
            f"/api/v1/users/{owner['id']}", headers={"X-CSRF-Token": csrf}, json=payload
        )
        assert response.status_code == 400, response.text
    deleted = client.delete(f"/api/v1/users/{owner['id']}", headers={"X-CSRF-Token": csrf})
    assert deleted.status_code == 400

    # With a second administrator present the first may step down.
    second = _create(client, csrf, email="second@example.com", is_admin=True).json()
    assert second["is_admin"] is True
    demoted = client.patch(
        f"/api/v1/users/{owner['id']}", headers={"X-CSRF-Token": csrf}, json={"is_admin": False}
    )
    # Still refused, because an administrator may not remove their own access.
    assert demoted.status_code == 400
    promoted = client.patch(
        f"/api/v1/users/{second['id']}", headers={"X-CSRF-Token": csrf}, json={"is_admin": False}
    )
    assert promoted.status_code == 200, promoted.text


def test_deleting_an_account_removes_the_vehicles_it_owned(
    registered: tuple[TestClient, str], db_factory: sessionmaker[Session]
) -> None:
    client, csrf = registered
    user = _create(client, csrf).json()
    session = TestClient(client.app)
    session.post(
        "/api/v1/auth/login",
        json={"email": "driver@example.com", "password": "another-long-password"},
    )
    token = session.cookies.get("vehinode_csrf")
    vehicle = session.post(
        "/api/v1/vehicles", headers={"X-CSRF-Token": token}, json={"name": "Their car"}
    )
    assert vehicle.status_code == 201, vehicle.text

    removed = client.delete(f"/api/v1/users/{user['id']}", headers={"X-CSRF-Token": csrf})
    assert removed.status_code == 204, removed.text
    assert all(row["id"] != user["id"] for row in client.get("/api/v1/users").json())

    # The vehicle and the sign-in identity go with the account rather than being
    # orphaned; the deletion confirmation in the interface says so.
    with db_factory() as db:
        assert db.scalars(select(Vehicle).where(Vehicle.owner_id == user["id"])).all() == []
        identities = select(AuthenticationIdentity).where(
            AuthenticationIdentity.user_id == user["id"]
        )
        assert db.scalars(identities).all() == []


def test_a_non_administrator_cannot_reach_the_endpoints(
    registered: tuple[TestClient, str],
) -> None:
    client, csrf = registered
    _create(client, csrf)
    session = TestClient(client.app)
    session.post(
        "/api/v1/auth/login",
        json={"email": "driver@example.com", "password": "another-long-password"},
    )
    token = session.cookies.get("vehinode_csrf")
    assert session.get("/api/v1/users").status_code == 403
    assert (
        session.post(
            "/api/v1/users",
            headers={"X-CSRF-Token": token},
            json={
                "email": "x@example.com",
                "display_name": "X",
                "password": "a-very-long-password",
            },
        ).status_code
        == 403
    )
