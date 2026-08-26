from fastapi import APIRouter, HTTPException, status

from backend.app.access.services import is_admin
from backend.app.auth.dependencies import CurrentUser, CurrentUserWrite, Db
from backend.app.vehicle_profiles.schemas import VehicleProfileResponse, VehicleProfileWrite
from backend.app.vehicle_profiles.services import (
    VehicleProfileError,
    built_in_definitions,
    can_edit_profile,
    create_profile,
    delete_profile,
    list_vehicle_profiles,
    profile_by_id,
    serialize_profile,
    update_profile,
)

router = APIRouter(prefix="/vehicle-profiles", tags=["vehicle profiles"])


@router.get("", response_model=list[VehicleProfileResponse])
def profiles(db: Db, auth: CurrentUser) -> list[VehicleProfileResponse]:
    return list_vehicle_profiles(db, auth.user)


@router.post("", response_model=VehicleProfileResponse, status_code=status.HTTP_201_CREATED)
def add_profile(
    data: VehicleProfileWrite, db: Db, auth: CurrentUserWrite
) -> VehicleProfileResponse:
    if not is_admin(auth.user) and not auth.user.can_create_profiles:
        raise HTTPException(status_code=403, detail="permission denied")
    try:
        profile = create_profile(db, auth.user.id, data)
    except VehicleProfileError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return serialize_profile(profile, auth.user)


@router.put("/{profile_id}", response_model=VehicleProfileResponse)
def edit_profile(
    profile_id: str, data: VehicleProfileWrite, db: Db, auth: CurrentUserWrite
) -> VehicleProfileResponse:
    if profile_id in built_in_definitions():
        raise HTTPException(status_code=403, detail="built-in profiles are read-only")
    profile = profile_by_id(db, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="vehicle profile not found")
    if not can_edit_profile(auth.user, profile):
        raise HTTPException(status_code=403, detail="permission denied")
    try:
        update_profile(db, profile, data)
    except VehicleProfileError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return serialize_profile(profile, auth.user)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_profile(profile_id: str, db: Db, auth: CurrentUserWrite) -> None:
    if profile_id in built_in_definitions():
        raise HTTPException(status_code=403, detail="built-in profiles are read-only")
    profile = profile_by_id(db, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="vehicle profile not found")
    if not can_edit_profile(auth.user, profile):
        raise HTTPException(status_code=403, detail="permission denied")
    delete_profile(db, profile)
    db.commit()
