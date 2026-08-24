from fastapi import APIRouter, HTTPException, status

from backend.app.auth.dependencies import CurrentUser, CurrentUserWrite, Db
from backend.app.vehicle_profiles.schemas import VehicleProfileResponse, VehicleProfileWrite
from backend.app.vehicle_profiles.services import (
    VehicleProfileError,
    create_profile,
    delete_profile,
    list_vehicle_profiles,
    owned_profile,
    update_profile,
)

router = APIRouter(prefix="/vehicle-profiles", tags=["vehicle profiles"])


@router.get("", response_model=list[VehicleProfileResponse])
def profiles(db: Db, auth: CurrentUser) -> list[VehicleProfileResponse]:
    return list_vehicle_profiles(db, auth.user.id)


@router.post("", response_model=VehicleProfileResponse, status_code=status.HTTP_201_CREATED)
def add_profile(
    data: VehicleProfileWrite, db: Db, auth: CurrentUserWrite
) -> VehicleProfileResponse:
    try:
        profile = create_profile(db, auth.user.id, data)
    except VehicleProfileError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return VehicleProfileResponse(
        id=profile.id,
        name=profile.name,
        description=profile.description,
        built_in=False,
        definition=profile.definition,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.put("/{profile_id}", response_model=VehicleProfileResponse)
def edit_profile(
    profile_id: str, data: VehicleProfileWrite, db: Db, auth: CurrentUserWrite
) -> VehicleProfileResponse:
    profile = owned_profile(db, auth.user.id, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="vehicle profile not found")
    try:
        update_profile(db, profile, data)
    except VehicleProfileError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return VehicleProfileResponse(
        id=profile.id,
        name=profile.name,
        description=profile.description,
        built_in=False,
        definition=profile.definition,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_profile(profile_id: str, db: Db, auth: CurrentUserWrite) -> None:
    profile = owned_profile(db, auth.user.id, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="vehicle profile not found")
    delete_profile(db, profile)
    db.commit()
