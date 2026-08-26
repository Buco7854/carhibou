from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.auth.dependencies import (
    AuthenticatedUser,
    Db,
    require_permission,
    require_permission_read,
)
from backend.app.auth.services import AuthenticationError, create_local_user
from backend.app.users.models import User
from backend.app.users.schemas import UserAccountResponse, UserCreate, UserUpdate
from backend.app.users.services import (
    UserAdministrationError,
    delete_user,
    is_admin,
    list_users,
    set_active,
    set_admin,
)

router = APIRouter(prefix="/users", tags=["users"])

AdminRead = Annotated[AuthenticatedUser, Depends(require_permission_read("system.admin"))]
AdminWrite = Annotated[AuthenticatedUser, Depends(require_permission("system.admin"))]


def _response(user: User) -> UserAccountResponse:
    return UserAccountResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        is_admin=is_admin(user),
        created_at=user.created_at,
    )


def _owned(db: Db, user_id: str) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return user


@router.get("", response_model=list[UserAccountResponse])
def list_accounts(db: Db, auth: AdminRead) -> list[UserAccountResponse]:
    del auth
    return [_response(user) for user in list_users(db)]


@router.post("", response_model=UserAccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(data: UserCreate, db: Db, auth: AdminWrite) -> UserAccountResponse:
    """Create an identity without reopening public registration.

    Self-registration only ever creates the first administrator, so this is the
    supported way to add anyone afterwards.
    """
    del auth
    try:
        user = create_local_user(
            db,
            email=data.email,
            password=data.password,
            display_name=data.display_name,
            admin=data.is_admin,
        )
    except AuthenticationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    db.commit()
    return _response(user)


@router.patch("/{user_id}", response_model=UserAccountResponse)
def update_account(user_id: str, data: UserUpdate, db: Db, auth: AdminWrite) -> UserAccountResponse:
    user = _owned(db, user_id)
    if user.id == auth.user.id and (data.is_admin is False or data.is_active is False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="an administrator cannot remove their own access",
        )
    try:
        if data.is_admin is not None:
            set_admin(db, user, data.is_admin)
        if data.is_active is not None:
            set_active(db, user, data.is_active)
    except UserAdministrationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    db.commit()
    return _response(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_account(user_id: str, db: Db, auth: AdminWrite) -> None:
    user = _owned(db, user_id)
    if user.id == auth.user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="an account cannot delete itself"
        )
    try:
        delete_user(db, user)
    except UserAdministrationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    db.commit()
