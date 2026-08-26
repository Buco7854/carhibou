from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.access.constants import SYSTEM_ADMIN
from backend.app.access.services import is_admin
from backend.app.users.models import User


class UserAdministrationError(Exception):
    pass


def list_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).order_by(User.created_at)))


def _other_active_admin_exists(db: Session, excluding: str) -> bool:
    for candidate in db.scalars(select(User).where(User.id != excluding)):
        if candidate.is_active and is_admin(candidate):
            return True
    return False


def _guard_last_admin(db: Session, user: User) -> None:
    """Refuse a change that would leave the instance with no way back in.

    An instance with no active administrator cannot be recovered from the browser:
    public registration only ever creates the first account, so there would be no
    one left who can restore access.
    """
    if not _other_active_admin_exists(db, user.id):
        raise UserAdministrationError("the last active administrator must remain")


def set_admin(db: Session, user: User, admin: bool) -> None:
    if is_admin(user) and not admin:
        _guard_last_admin(db, user)
    permissions = dict(user.permissions)
    if admin:
        permissions[SYSTEM_ADMIN] = True
    else:
        permissions.pop(SYSTEM_ADMIN, None)
    user.permissions = permissions


def set_active(db: Session, user: User, active: bool) -> None:
    if user.is_active and not active and is_admin(user):
        _guard_last_admin(db, user)
    user.is_active = active


def delete_user(db: Session, user: User) -> None:
    if is_admin(user):
        _guard_last_admin(db, user)
    db.delete(user)
