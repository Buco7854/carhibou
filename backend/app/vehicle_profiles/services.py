from copy import deepcopy
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy import select, update
from sqlalchemy.orm import Session

import agent
from agent.vehicle_agent.profile_decoder import ProfileError, VehicleProfileDecoder
from backend.app.access.services import is_admin
from backend.app.common.ids import new_id
from backend.app.devices.models import Device
from backend.app.users.models import User
from backend.app.vehicle_profiles.models import VehicleProfile
from backend.app.vehicle_profiles.schemas import (
    ProfileDefinition,
    VehicleProfileResponse,
    VehicleProfileWrite,
)
from backend.app.vehicles.models import Vehicle


class VehicleProfileError(ValueError):
    pass


@lru_cache(maxsize=1)
def built_in_definitions() -> dict[str, dict[str, object]]:
    directory = Path(agent.__file__).resolve().parent / "profiles"
    definitions: dict[str, dict[str, object]] = {}
    for path in sorted(directory.glob("*.yaml")):
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        definition = ProfileDefinition.model_validate(loaded)
        dumped = definition.model_dump(exclude_none=True)
        VehicleProfileDecoder(dumped)
        definitions[definition.id] = dumped
    return definitions


def _definition(profile_id: str, data: VehicleProfileWrite) -> dict[str, object]:
    definition = ProfileDefinition(
        id=profile_id,
        name=data.name,
        version=1,
        description=data.description,
        signals=[signal.model_dump(exclude_none=True) for signal in data.signals],
        computed_metrics=data.computed_metrics,
    ).model_dump(exclude_none=True)
    try:
        VehicleProfileDecoder(definition)
    except (ProfileError, KeyError, TypeError, ValueError) as exc:
        raise VehicleProfileError(str(exc)) from exc
    return definition


def list_vehicle_profiles(db: Session, user: User) -> list[VehicleProfileResponse]:
    built_ins = [
        VehicleProfileResponse(
            id=profile_id,
            name=str(definition["name"]),
            description=str(definition.get("description", "")),
            built_in=True,
            editable=False,
            definition=deepcopy(definition),
        )
        for profile_id, definition in built_in_definitions().items()
    ]
    custom = [
        VehicleProfileResponse(
            id=profile.id,
            name=profile.name,
            description=profile.description,
            built_in=False,
            editable=can_edit_profile(user, profile),
            definition=deepcopy(profile.definition),
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )
        for profile in db.scalars(select(VehicleProfile).order_by(VehicleProfile.created_at))
    ]
    return [*built_ins, *custom]


def profile_by_id(db: Session, profile_id: str) -> VehicleProfile | None:
    return db.get(VehicleProfile, profile_id)


def can_edit_profile(user: User, profile: VehicleProfile) -> bool:
    return is_admin(user) or profile.created_by == user.id


def serialize_profile(profile: VehicleProfile, user: User) -> VehicleProfileResponse:
    return VehicleProfileResponse(
        id=profile.id,
        name=profile.name,
        description=profile.description,
        built_in=False,
        editable=can_edit_profile(user, profile),
        definition=deepcopy(profile.definition),
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


# The keys a decoder reads. A profile also carries what people need to recognise
# it in the interface - its name, family, version and per-signal display names and
# descriptions - and none of that reaches a decoder. Sending it anyway more than
# doubled the configuration an agent downloads on every sync and holds in memory
# while parsing, which is worth avoiding on a single-core 512MB board.
_AGENT_SIGNAL_KEYS = frozenset({"name", "source", "decoder", "unit", "minimum", "maximum"})
_AGENT_COMPUTED_KEYS = frozenset({"name", "operation", "inputs", "unit", "scale"})


def agent_definition(definition: dict[str, object]) -> dict[str, object]:
    """Project a profile down to the fields an agent's decoder actually reads."""

    signals = definition.get("signals")
    computed = definition.get("computed_metrics")
    projected: dict[str, object] = {
        "id": definition["id"],
        "signals": [
            {key: value for key, value in signal.items() if key in _AGENT_SIGNAL_KEYS}
            for signal in (signals if isinstance(signals, list) else [])
        ],
    }
    if isinstance(computed, list) and computed:
        projected["computed_metrics"] = [
            {key: value for key, value in metric.items() if key in _AGENT_COMPUTED_KEYS}
            for metric in computed
        ]
    return projected


def profile_definition(db: Session, profile_id: str | None) -> dict[str, object] | None:
    if not profile_id:
        return None
    built_in = built_in_definitions().get(profile_id)
    if built_in:
        return agent_definition(built_in)
    profile = profile_by_id(db, profile_id)
    return agent_definition(profile.definition) if profile else None


def create_profile(db: Session, creator_id: str, data: VehicleProfileWrite) -> VehicleProfile:
    profile_id = new_id()
    profile = VehicleProfile(
        id=profile_id,
        created_by=creator_id,
        name=data.name,
        description=data.description,
        definition=_definition(profile_id, data),
    )
    db.add(profile)
    db.flush()
    return profile


def _bump_assigned_devices(db: Session, profile_id: str) -> None:
    vehicle_ids = select(Vehicle.id).where(Vehicle.vehicle_profile == profile_id)
    db.execute(
        update(Device)
        .where(Device.vehicle_id.in_(vehicle_ids))
        .values(config_version=Device.config_version + 1)
    )


def update_profile(db: Session, profile: VehicleProfile, data: VehicleProfileWrite) -> None:
    profile.name = data.name
    profile.description = data.description
    current_version = int(profile.definition.get("version", 1))
    definition = _definition(profile.id, data)
    definition["version"] = current_version + 1
    profile.definition = definition
    _bump_assigned_devices(db, profile.id)


def delete_profile(db: Session, profile: VehicleProfile) -> None:
    _bump_assigned_devices(db, profile.id)
    db.execute(
        update(Vehicle).where(Vehicle.vehicle_profile == profile.id).values(vehicle_profile=None)
    )
    db.delete(profile)


def assign_profile(db: Session, vehicle: Vehicle, profile_id: str | None) -> None:
    if profile_id == vehicle.vehicle_profile:
        return
    vehicle.vehicle_profile = profile_id
    db.execute(
        update(Device)
        .where(Device.vehicle_id == vehicle.id)
        .values(config_version=Device.config_version + 1)
    )
