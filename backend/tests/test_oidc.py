import logging
from asyncio import run
from collections.abc import Mapping
from typing import cast

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.access.models import VehicleAccessGrant
from backend.app.access.schemas import DefaultAccess, DefaultVehicleGrant
from backend.app.access.services import is_admin, set_default_access
from backend.app.auth import oidc as oidc_service
from backend.app.auth import routes as auth_routes
from backend.app.auth.models import AuthenticationIdentity
from backend.app.auth.oidc import (
    OIDCAuthenticationError,
    authenticate_oidc_claims,
    validated_oidc_claims,
)
from backend.app.auth.services import create_local_user
from backend.app.common.settings import Settings
from backend.app.users.models import User
from backend.app.vehicles.models import Vehicle


def _settings(**updates: object) -> Settings:
    return Settings(_env_file=None).model_copy(
        update={
            "oidc_issuer": "https://identity.example.com",
            "oidc_client_id": "vehinode",
            **updates,
        }
    )


def _oidc_identity(user: User, subject: str) -> AuthenticationIdentity:
    return AuthenticationIdentity(
        user_id=user.id,
        provider="oidc",
        subject=subject,
        password_hash=None,
    )


def test_oidc_environment_variables_are_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VEHINODE_OIDC_ISSUER", "https://login.example.com")
    monkeypatch.setenv("VEHINODE_OIDC_CLIENT_ID", "client-id")
    monkeypatch.setenv("VEHINODE_OIDC_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("VEHINODE_OIDC_SCOPES", "openid email custom")
    monkeypatch.setenv("VEHINODE_OIDC_GROUP_CLAIM", "roles")
    monkeypatch.setenv("VEHINODE_OIDC_ADMIN_GROUP", "administrators")
    monkeypatch.setenv("VEHINODE_OIDC_AUTO_PROVISION", "false")
    monkeypatch.setenv("VEHINODE_OIDC_DISPLAY_NAME", "Corporate SSO")

    settings = Settings(_env_file=None)

    assert settings.oidc_enabled
    assert settings.oidc_issuer == "https://login.example.com"
    assert settings.oidc_client_id == "client-id"
    assert settings.oidc_client_secret is not None
    assert settings.oidc_client_secret.get_secret_value() == "client-secret"
    assert settings.oidc_scopes == "openid email custom"
    assert settings.oidc_group_claim == "roles"
    assert settings.oidc_admin_group == "administrators"
    assert settings.oidc_auto_provision is False
    assert settings.oidc_display_name == "Corporate SSO"


def test_authlib_exchange_requires_configured_issuer_and_audience(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TokenBoundary:
        claims_options: dict[str, dict[str, list[str]]] | None = None

        async def authorize_access_token(
            self, _request: Request, **kwargs: object
        ) -> dict[str, object]:
            self.claims_options = cast(dict[str, dict[str, list[str]]], kwargs["claims_options"])
            return {"userinfo": {"sub": "validated-subject"}}

    boundary = TokenBoundary()
    monkeypatch.setattr(oidc_service, "_client", lambda _settings_value: boundary)
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})

    claims = run(validated_oidc_claims(request, _settings()))

    assert claims["sub"] == "validated-subject"
    assert boundary.claims_options == {
        "iss": {"values": ["https://identity.example.com"]},
        "aud": {"values": ["vehinode"]},
    }


def test_oidc_client_uses_discovery_and_pkce() -> None:
    client = oidc_service._client(_settings())

    assert client.client_kwargs["scope"] == "openid email profile"
    assert client.client_kwargs["code_challenge_method"] == "S256"
    assert (
        client._server_metadata_url
        == "https://identity.example.com/.well-known/openid-configuration"
    )


def test_existing_oidc_identity_is_matched_before_email(
    db_factory: sessionmaker[Session],
) -> None:
    with db_factory() as db:
        user = User(email="linked@example.com", display_name="Linked", permissions={})
        db.add(user)
        db.flush()
        identity = _oidc_identity(user, "subject-1")
        db.add(identity)
        db.flush()

        authenticated = authenticate_oidc_claims(
            db,
            {"sub": "subject-1", "email": "different@example.com"},
            _settings(),
        )

        assert authenticated.id == user.id
        assert identity.last_used_at is not None
        assert len(list(db.scalars(select(User)))) == 1


def test_verified_email_links_oidc_identity(db_factory: sessionmaker[Session]) -> None:
    with db_factory() as db:
        user = create_local_user(
            db,
            "linked@example.com",
            "long-enough-password",
            "Linked",
            admin=False,
        )
        db.flush()

        authenticated = authenticate_oidc_claims(
            db,
            {
                "sub": "subject-2",
                "email": "LINKED@example.com",
                "email_verified": True,
            },
            _settings(),
        )

        identity = db.scalar(
            select(AuthenticationIdentity).where(
                AuthenticationIdentity.provider == "oidc",
                AuthenticationIdentity.subject == "subject-2",
            )
        )
        assert authenticated.id == user.id
        assert identity is not None
        assert identity.user_id == user.id


def test_unverified_email_cannot_link_an_account(db_factory: sessionmaker[Session]) -> None:
    with db_factory() as db:
        create_local_user(
            db,
            "linked@example.com",
            "long-enough-password",
            "Linked",
            admin=False,
        )

        with pytest.raises(OIDCAuthenticationError, match="not verified"):
            authenticate_oidc_claims(
                db,
                {
                    "sub": "subject-unverified",
                    "email": "linked@example.com",
                    "email_verified": False,
                },
                _settings(),
            )


def test_auto_provision_applies_default_access(db_factory: sessionmaker[Session]) -> None:
    with db_factory() as db:
        vehicle = Vehicle(name="Shared vehicle")
        db.add(vehicle)
        db.flush()
        set_default_access(
            db,
            DefaultAccess(
                profiles_create=True,
                grants=[DefaultVehicleGrant(vehicle_id=vehicle.id, level="operate")],
            ),
        )

        user = authenticate_oidc_claims(
            db,
            {
                "sub": "new-subject",
                "email": "new@example.com",
                "email_verified": True,
                "name": "New Driver",
            },
            _settings(),
        )

        grant = db.scalar(
            select(VehicleAccessGrant).where(
                VehicleAccessGrant.user_id == user.id,
                VehicleAccessGrant.vehicle_id == vehicle.id,
            )
        )
        assert user.display_name == "New Driver"
        assert user.can_create_profiles is True
        assert grant is not None
        assert grant.level == "operate"


def test_auto_provision_can_be_disabled(db_factory: sessionmaker[Session]) -> None:
    with db_factory() as db:
        with pytest.raises(OIDCAuthenticationError, match="provisioning is disabled"):
            authenticate_oidc_claims(
                db,
                {
                    "sub": "unknown-subject",
                    "email": "unknown@example.com",
                    "email_verified": True,
                },
                _settings(oidc_auto_provision=False),
            )
        assert db.scalar(select(User)) is None
        assert db.scalar(select(AuthenticationIdentity)) is None


def test_admin_group_promotes_on_each_login(db_factory: sessionmaker[Session]) -> None:
    with db_factory() as db:
        user = User(email="member@example.com", display_name="Member", permissions={})
        db.add(user)
        db.flush()
        db.add(_oidc_identity(user, "admin-subject"))
        db.flush()

        authenticate_oidc_claims(
            db,
            {"sub": "admin-subject", "roles": ["drivers", "vehinode-admins"]},
            _settings(oidc_group_claim="roles", oidc_admin_group="vehinode-admins"),
        )

        assert is_admin(user)


def test_last_admin_group_demotion_is_skipped_and_logged(
    db_factory: sessionmaker[Session], caplog: pytest.LogCaptureFixture
) -> None:
    with db_factory() as db:
        user = User(
            email="admin@example.com",
            display_name="Administrator",
            permissions={"system.admin": True},
        )
        db.add(user)
        db.flush()
        db.add(_oidc_identity(user, "last-admin"))
        db.flush()

        with caplog.at_level(logging.WARNING, logger="backend.app.auth.oidc"):
            authenticate_oidc_claims(
                db,
                {"sub": "last-admin", "groups": ["drivers"]},
                _settings(oidc_admin_group="vehinode-admins"),
            )

        assert is_admin(user)
        assert "last active administrator" in caplog.text


def test_auth_methods_reports_disabled_and_enabled_configurations(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    disabled = _settings(oidc_issuer="", oidc_display_name="Company Login")
    monkeypatch.setattr(auth_routes, "get_settings", lambda: disabled)
    assert client.get("/api/v1/auth/methods").json() == {
        "password": True,
        "oidc": {"enabled": False, "name": "Company Login"},
    }

    enabled = _settings(oidc_display_name="Company Login")
    monkeypatch.setattr(auth_routes, "get_settings", lambda: enabled)
    assert client.get("/api/v1/auth/methods").json() == {
        "password": True,
        "oidc": {"enabled": True, "name": "Company Login"},
    }


def test_oidc_callback_provisions_user_and_creates_normal_browser_session(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(public_url="http://testserver")

    async def claims_boundary(_request: Request, _settings_value: Settings) -> Mapping[str, object]:
        return {
            "sub": "callback-subject",
            "email": "callback@example.com",
            "email_verified": True,
            "name": "Callback User",
        }

    monkeypatch.setattr(auth_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(auth_routes, "validated_oidc_claims", claims_boundary)

    callback = client.get("/api/v1/auth/oidc/callback", follow_redirects=False)

    assert callback.status_code == 302
    assert callback.headers["location"] == "http://testserver/"
    assert "vehinode_session" in client.cookies
    assert "vehinode_csrf" in client.cookies
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "callback@example.com"
    assert client.post("/api/v1/auth/logout").status_code == 403
    assert (
        client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": client.cookies["vehinode_csrf"]},
        ).status_code
        == 204
    )


def test_oidc_configuration_closes_public_registration(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.app.auth import services as auth_services

    settings = _settings()
    monkeypatch.setattr(auth_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(auth_services, "get_settings", lambda: settings)

    assert client.get("/api/v1/auth/setup").json() == {"registration_open": False}
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "local@example.com",
            "password": "long-enough-password",
            "display_name": "Local User",
        },
    )
    assert response.status_code == 403
