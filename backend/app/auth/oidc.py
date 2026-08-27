import logging
from collections.abc import Mapping, Sequence
from typing import cast

from authlib.integrations.starlette_client import OAuth, OAuthError, StarletteOAuth2App
from joserfc.errors import JoseError
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import RedirectResponse

from backend.app.access.services import apply_default_access, is_admin
from backend.app.auth.models import AuthenticationIdentity
from backend.app.auth.services import _lock_user_creation
from backend.app.common.settings import Settings
from backend.app.common.time import utcnow
from backend.app.users.models import User
from backend.app.users.services import UserAdministrationError, set_admin

logger = logging.getLogger(__name__)


class OIDCAuthenticationError(Exception):
    pass


def _client(settings: Settings) -> StarletteOAuth2App:
    oauth = OAuth()
    issuer = settings.oidc_issuer.strip()
    secret = settings.oidc_client_secret.get_secret_value() if settings.oidc_client_secret else None
    registered = oauth.register(
        "oidc",
        client_id=settings.oidc_client_id.strip(),
        client_secret=secret,
        server_metadata_url=f"{issuer.rstrip('/')}/.well-known/openid-configuration",
        token_endpoint_auth_method="client_secret_basic" if secret else "none",
        client_kwargs={
            "scope": " ".join(settings.oidc_scopes.split()),
            "code_challenge_method": "S256",
        },
    )
    if not isinstance(registered, StarletteOAuth2App):
        raise RuntimeError("OIDC client registration failed")
    return registered


def oidc_callback_url(settings: Settings) -> str:
    return f"{settings.public_url.rstrip('/')}/api/v1/auth/oidc/callback"


async def oidc_login_redirect(request: Request, settings: Settings) -> RedirectResponse:
    return cast(
        RedirectResponse,
        await _client(settings).authorize_redirect(request, oidc_callback_url(settings)),
    )


async def validated_oidc_claims(request: Request, settings: Settings) -> Mapping[str, object]:
    client = _client(settings)
    try:
        metadata = await client.load_server_metadata()
        metadata_issuer = metadata.get("issuer")
        if not isinstance(metadata_issuer, str) or not metadata_issuer:
            raise OIDCAuthenticationError(
                "OIDC discovery issuer check failed: server metadata has no issuer"
            )
        token = cast(
            dict[str, object],
            await client.authorize_access_token(
                request,
                claims_options={
                    "iss": {"values": [metadata_issuer]},
                    "aud": {"values": [settings.oidc_client_id.strip()]},
                },
            ),
        )
    except OIDCAuthenticationError:
        raise
    except (JoseError, OAuthError) as exc:
        raise OIDCAuthenticationError(
            "OIDC ID token signature or claim validation check failed"
        ) from exc
    claims = token.get("userinfo")
    if not isinstance(claims, Mapping):
        raise OIDCAuthenticationError(
            "OIDC ID token result check failed: provider returned no validated user information"
        )
    return cast(Mapping[str, object], claims)


def _subject(claims: Mapping[str, object]) -> str:
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip() or len(subject) > 320:
        raise OIDCAuthenticationError("OIDC subject claim check failed: sub is missing or invalid")
    return subject


def _verified_email(claims: Mapping[str, object]) -> str:
    if claims.get("email_verified") is not True:
        raise OIDCAuthenticationError(
            "OIDC email verification check failed: email is not verified because "
            "email_verified is not true"
        )
    email = claims.get("email")
    if not isinstance(email, str):
        raise OIDCAuthenticationError("OIDC email claim check failed: email is missing")
    try:
        return str(TypeAdapter(EmailStr).validate_python(email)).strip().lower()
    except ValidationError as exc:
        raise OIDCAuthenticationError("OIDC email claim check failed: email is invalid") from exc


def _display_name(claims: Mapping[str, object], email: str) -> str:
    for claim_name in ("name", "preferred_username"):
        value = claims.get(claim_name)
        if isinstance(value, str) and value.strip():
            return value.strip()[:120]
    return email[:120]


def _groups(claims: Mapping[str, object], claim_name: str) -> set[str]:
    value = claims.get(claim_name)
    if isinstance(value, str):
        return {value}
    if isinstance(value, Sequence):
        return {group for group in value if isinstance(group, str)}
    return set()


def _map_admin_group(
    db: Session, user: User, claims: Mapping[str, object], settings: Settings
) -> None:
    admin_group = settings.oidc_admin_group.strip()
    if not admin_group:
        return
    desired = admin_group in _groups(claims, settings.oidc_group_claim.strip())
    if is_admin(user) == desired:
        return
    try:
        set_admin(db, user, desired)
    except UserAdministrationError:
        logger.warning(
            "OIDC admin demotion skipped because the account is the last active administrator",
            extra={"user_id": user.id},
        )


def _identity_user(db: Session, subject: str) -> tuple[AuthenticationIdentity, User] | None:
    identity = db.scalar(
        select(AuthenticationIdentity).where(
            AuthenticationIdentity.provider == "oidc",
            AuthenticationIdentity.subject == subject,
        )
    )
    if not identity:
        return None
    user = db.get(User, identity.user_id)
    if not user:
        raise OIDCAuthenticationError(
            "OIDC identity account check failed: linked account does not exist"
        )
    return identity, user


def _finish_login(
    db: Session,
    identity: AuthenticationIdentity,
    user: User,
    claims: Mapping[str, object],
    settings: Settings,
) -> User:
    if not user.is_active:
        raise OIDCAuthenticationError("OIDC account status check failed: account is inactive")
    identity.last_used_at = utcnow()
    _map_admin_group(db, user, claims, settings)
    return user


def authenticate_oidc_claims(db: Session, claims: Mapping[str, object], settings: Settings) -> User:
    subject = _subject(claims)
    matched = _identity_user(db, subject)
    if matched:
        identity, matched_user = matched
        return _finish_login(db, identity, matched_user, claims, settings)

    email = _verified_email(claims)
    _lock_user_creation(db)

    # Recheck after the PostgreSQL creation lock so concurrent first logins
    # cannot provision two accounts or link the same provider identity twice.
    matched = _identity_user(db, subject)
    if matched:
        identity, matched_user = matched
        return _finish_login(db, identity, matched_user, claims, settings)

    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if not user:
        if not settings.oidc_auto_provision:
            raise OIDCAuthenticationError(
                "OIDC account provisioning check failed: automatic provisioning is disabled"
            )
        user = User(email=email, display_name=_display_name(claims, email), permissions={})
        db.add(user)
        db.flush()
        apply_default_access(db, user)

    identity = AuthenticationIdentity(
        user_id=user.id,
        provider="oidc",
        subject=subject,
        password_hash=None,
    )
    db.add(identity)
    db.flush()
    return _finish_login(db, identity, user, claims, settings)
