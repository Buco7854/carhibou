from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from backend.app.access.dependencies import RequireAdmin, RequireAdminWrite
from backend.app.auth.dependencies import Db
from backend.app.secrets.crypto import encrypt_secret
from backend.app.secrets.models import Secret
from backend.app.secrets.schemas import SecretResponse, SecretWrite

router = APIRouter(prefix="/secrets", tags=["hook secrets"])


@router.get("", response_model=list[SecretResponse])
def list_secrets(db: Db, auth: RequireAdmin) -> list[Secret]:
    del auth
    return list(db.scalars(select(Secret).order_by(Secret.name)))


@router.put("/{name}", response_model=SecretResponse)
def set_secret(name: str, data: SecretWrite, db: Db, auth: RequireAdminWrite) -> Secret:
    del auth
    if name != data.name:
        raise HTTPException(status_code=400, detail="secret name in path and body must match")
    model = db.scalar(select(Secret).where(Secret.name == name))
    encrypted = encrypt_secret(data.value)
    if model:
        model.encrypted_value = encrypted
    else:
        model = Secret(name=name, encrypted_value=encrypted)
        db.add(model)
    db.commit()
    return model


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_secret(name: str, db: Db, auth: RequireAdminWrite) -> None:
    del auth
    model = db.scalar(select(Secret).where(Secret.name == name))
    if not model:
        raise HTTPException(status_code=404, detail="secret not found")
    db.delete(model)
    db.commit()
