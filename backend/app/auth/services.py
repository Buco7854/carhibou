from dataclasses import dataclass
from datetime import timedelta

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from backend.app.access.constants import SYSTEM_ADMIN
from backend.app.access.services import apply_default_access
from backend.app.auth.models import AuthenticationIdentity, BrowserSession
from backend.app.auth.provider import AuthenticatedIdentity
from backend.app.auth.security import (
    hash_password,
    hash_token,
    new_opaque_token,
    verify_password,
)
from backend.app.common.settings import get_settings
from backend.app.common.time import utcnow
from backend.app.users.models import User


class AuthenticationError(Exception):
    pass


class RegistrationClosedError(Exception):
    pass


@dataclass(frozen=True)
class NewSession:
    model: BrowserSession
    token: str
    csrf_token: str


class LocalAuthenticationProvider:
    name = "local"

    def __init__(self, db: Session):
        self.db = db

    def authenticate(self, subject: str, credential: str) -> AuthenticatedIdentity | None:
        normalized = subject.strip().lower()
        identity = self.db.scalar(
            select(AuthenticationIdentity).where(
                AuthenticationIdentity.provider == self.name,
                AuthenticationIdentity.subject == normalized,
            )
        )
        if not identity or not identity.password_hash:
            return None
        if not verify_password(identity.password_hash, credential):
            return None
        identity.last_used_at = utcnow()
        return AuthenticatedIdentity(self.name, identity.subject, identity.user_id)


def _lock_user_creation(db: Session) -> None:
    if db.get_bind().dialect.name == "postgresql":
        # Serializes the one-time first-admin decision and duplicate checks.
        db.execute(text("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE"))


def create_local_user(
    db: Session,
    email: str,
    password: str,
    display_name: str,
    *,
    admin: bool,
) -> User:
    try:
        normalized = str(TypeAdapter(EmailStr).validate_python(email)).strip().lower()
    except ValidationError as exc:
        raise AuthenticationError("email is invalid") from exc
    normalized_name = display_name.strip()
    if not normalized_name or len(normalized_name) > 120:
        raise AuthenticationError("display name must contain between 1 and 120 characters")
    if len(password) < 12 or len(password) > 256:
        raise AuthenticationError("password must contain between 12 and 256 characters")
    if db.scalar(select(User.id).where(func.lower(User.email) == normalized)):
        raise AuthenticationError("email is already registered")
    permissions = {SYSTEM_ADMIN: True} if admin else {}
    user = User(email=normalized, display_name=normalized_name, permissions=permissions)
    db.add(user)
    db.flush()
    apply_default_access(db, user)
    db.add(
        AuthenticationIdentity(
            user_id=user.id,
            provider="local",
            subject=normalized,
            password_hash=hash_password(password),
        )
    )
    return user


def registration_is_open(db: Session) -> bool:
    return db.scalar(select(func.count(User.id))) == 0


def register_first_local_admin(db: Session, email: str, password: str, display_name: str) -> User:
    _lock_user_creation(db)
    if not registration_is_open(db):
        raise RegistrationClosedError
    return create_local_user(db, email, password, display_name, admin=True)


def bootstrap_local_admin(db: Session, email: str, password: str, display_name: str) -> User | None:
    """Create the only self-registerable local administrator, once."""

    try:
        return register_first_local_admin(db, email, password, display_name)
    except RegistrationClosedError:
        return None


def create_session(
    db: Session, user: User, ip_address: str | None, user_agent: str | None
) -> NewSession:
    settings = get_settings()
    token = new_opaque_token("vs")
    csrf = new_opaque_token("csrf")
    now = utcnow()
    model = BrowserSession(
        token_hash=hash_token(token),
        csrf_hash=hash_token(csrf),
        user_id=user.id,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=settings.session_ttl_hours),
        ip_address=ip_address,
        user_agent=(user_agent or "")[:512] or None,
    )
    db.add(model)
    db.flush()
    return NewSession(model=model, token=token, csrf_token=csrf)


def change_password(db: Session, user_id: str, current: str, new: str) -> None:
    identity = db.scalar(
        select(AuthenticationIdentity).where(
            AuthenticationIdentity.user_id == user_id,
            AuthenticationIdentity.provider == "local",
        )
    )
    if (
        not identity
        or not identity.password_hash
        or not verify_password(identity.password_hash, current)
    ):
        raise AuthenticationError("current password is incorrect")
    identity.password_hash = hash_password(new)


def revoke_other_sessions(db: Session, user_id: str, current_id: str) -> None:
    db.execute(
        update(BrowserSession)
        .where(
            BrowserSession.user_id == user_id,
            BrowserSession.id != current_id,
            BrowserSession.revoked_at.is_(None),
        )
        .values(revoked_at=utcnow())
    )
