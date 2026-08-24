from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from backend.app.auth.dependencies import (
    AuthenticatedUser,
    Db,
    require_permission,
    require_permission_read,
)
from backend.app.secrets.crypto import encrypt_secret
from backend.app.secrets.models import Secret
from backend.app.secrets.schemas import SecretResponse, SecretWrite

ManageHooks = Annotated[AuthenticatedUser, Depends(require_permission("hooks.manage_code"))]
ViewHooks = Annotated[AuthenticatedUser, Depends(require_permission_read("hooks.manage_code"))]
router = APIRouter(prefix="/secrets", tags=["hook secrets"])


@router.get("", response_model=list[SecretResponse])
def list_secrets(db: Db, auth: ViewHooks) -> list[Secret]:
    return list(
        db.scalars(select(Secret).where(Secret.owner_id == auth.user.id).order_by(Secret.name))
    )


@router.put("/{name}", response_model=SecretResponse)
def set_secret(name: str, data: SecretWrite, db: Db, auth: ManageHooks) -> Secret:
    if name != data.name:
        raise HTTPException(status_code=400, detail="secret name in path and body must match")
    model = db.scalar(select(Secret).where(Secret.owner_id == auth.user.id, Secret.name == name))
    encrypted = encrypt_secret(data.value)
    if model:
        model.encrypted_value = encrypted
    else:
        model = Secret(owner_id=auth.user.id, name=name, encrypted_value=encrypted)
        db.add(model)
    db.commit()
    return model


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_secret(name: str, db: Db, auth: ManageHooks) -> None:
    model = db.scalar(select(Secret).where(Secret.owner_id == auth.user.id, Secret.name == name))
    if not model:
        raise HTTPException(status_code=404, detail="secret not found")
    db.delete(model)
    db.commit()
