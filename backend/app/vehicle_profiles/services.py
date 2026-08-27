from copy import deepcopy
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy import select, update
from sqlalchemy.orm import Session

import agent
from agent.vehicle_agent.profile_decoder import ProfileError, VehicleProfileDecoder
from backend.app.access.services import is_admin
from backend.app.agents.models import Agent
from backend.app.common.ids import new_id
from backend.app.connectors.constants import DEFAULT_MAPPING_PROFILES
from backend.app.connectors.models import Connector
from backend.app.users.models import User
from backend.app.vehicle_profiles.mapping import MappingEngine
from backend.app.vehicle_profiles.models import VehicleProfile
from backend.app.vehicle_profiles.schemas import (
    PROFILE_DEFINITION_ADAPTER,
    CanProfileDefinition,
    CanProfileWrite,
    MappingProfileDefinition,
    VehicleProfileResponse,
    VehicleProfileWrite,
)


class VehicleProfileError(ValueError):
    pass


@lru_cache(maxsize=1)
def built_in_definitions() -> dict[str, dict[str, object]]:
    directory = Path(agent.__file__).resolve().parent / "profiles"
    definitions: dict[str, dict[str, object]] = {}
    for path in sorted(directory.glob("*.yaml")):
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        definition = PROFILE_DEFINITION_ADAPTER.validate_python(loaded)
        dumped = definition.model_dump(exclude_none=True, by_alias=True)
        if definition.id in definitions:
            raise VehicleProfileError(f"duplicate built-in profile id {definition.id!r}")
        if isinstance(definition, CanProfileDefinition):
            VehicleProfileDecoder(dumped)
        else:
            MappingEngine(definition)
        definitions[definition.id] = dumped
    return definitions


def _definition(profile_id: str, data: VehicleProfileWrite) -> dict[str, object]:
    if isinstance(data, CanProfileWrite):
        definition = CanProfileDefinition(
            id=profile_id,
            name=data.name,
            version=1,
            description=data.description,
            type="can",
            signals=data.signals,
            computed_metrics=data.computed_metrics,
        )
        dumped = definition.model_dump(exclude_none=True)
        try:
            VehicleProfileDecoder(dumped)
        except (ProfileError, KeyError, TypeError, ValueError) as exc:
            raise VehicleProfileError(str(exc)) from exc
        return dumped
    mapping_definition = MappingProfileDefinition(
        id=profile_id,
        name=data.name,
        version=1,
        description=data.description,
        type="mapping",
        passthrough_prefix=data.passthrough_prefix,
        ignore=data.ignore,
        rules=data.rules,
    )
    MappingEngine(mapping_definition)
    return mapping_definition.model_dump(exclude_none=True, by_alias=True)


def list_vehicle_profiles(db: Session, user: User) -> list[VehicleProfileResponse]:
    built_ins = [
        VehicleProfileResponse(
            id=profile_id,
            name=str(definition["name"]),
            description=str(definition.get("description", "")),
            type=str(definition["type"]),
            built_in=True,
            editable=False,
            definition=deepcopy(definition),
        )
        for profile_id, definition in built_in_definitions().items()
    ]
    custom = [serialize_profile(profile, user) for profile in db.scalars(select(VehicleProfile))]
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
        type=profile.type,
        built_in=False,
        editable=can_edit_profile(user, profile),
        definition=deepcopy(profile.definition),
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


# The keys a decoder reads. A profile also carries what people need to recognise
# it in the interface, including its name, version and per-signal display names,
# and none of that reaches a decoder. Sending it anyway more than doubled the
# configuration an agent downloads on every sync and holds in memory while
# parsing, which is worth avoiding on a single-core 512MB board.
_AGENT_SIGNAL_KEYS = frozenset({"name", "source", "decoder", "unit", "minimum", "maximum"})
_AGENT_COMPUTED_KEYS = frozenset({"name", "operation", "inputs", "unit", "scale"})


def agent_definition(definition: dict[str, object]) -> dict[str, object]:
    """Project a CAN profile down to the fields an agent's decoder actually reads."""

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


def full_profile_definition(
    db: Session, profile_id: str | None, expected_type: str
) -> dict[str, object] | None:
    if not profile_id:
        return None
    definition = built_in_definitions().get(profile_id)
    if definition:
        return deepcopy(definition) if definition.get("type") == expected_type else None
    profile = profile_by_id(db, profile_id)
    if not profile or profile.type != expected_type:
        return None
    return deepcopy(profile.definition)


def can_profile_definition(db: Session, profile_id: str | None) -> dict[str, object] | None:
    definition = full_profile_definition(db, profile_id, "can")
    return agent_definition(definition) if definition else None


def mapping_profile_definition(
    db: Session, profile_id: str | None
) -> MappingProfileDefinition | None:
    definition = full_profile_definition(db, profile_id, "mapping")
    if not definition:
        return None
    parsed = PROFILE_DEFINITION_ADAPTER.validate_python(definition)
    return parsed if isinstance(parsed, MappingProfileDefinition) else None


def create_profile(db: Session, creator_id: str, data: VehicleProfileWrite) -> VehicleProfile:
    profile_id = new_id()
    profile = VehicleProfile(
        id=profile_id,
        created_by=creator_id,
        name=data.name,
        description=data.description,
        type=data.type,
        definition=_definition(profile_id, data),
    )
    db.add(profile)
    db.flush()
    return profile


def _bump_assigned_agents(db: Session, profile_id: str) -> None:
    db.execute(
        update(Agent)
        .where(Agent.vehicle_profile == profile_id)
        .values(config_version=Agent.config_version + 1)
    )


def _bump_assigned_connectors(db: Session, profile_id: str) -> None:
    db.execute(
        update(Connector)
        .where(Connector.mapping_profile == profile_id)
        .values(config_version=Connector.config_version + 1)
    )


def update_profile(db: Session, profile: VehicleProfile, data: VehicleProfileWrite) -> None:
    if data.type != profile.type:
        raise VehicleProfileError("profile type cannot be changed")
    profile.name = data.name
    profile.description = data.description
    current_version = int(profile.definition.get("version", 1))
    definition = _definition(profile.id, data)
    definition["version"] = current_version + 1
    profile.definition = definition
    if profile.type == "can":
        _bump_assigned_agents(db, profile.id)
    else:
        _bump_assigned_connectors(db, profile.id)


def delete_profile(db: Session, profile: VehicleProfile) -> None:
    if profile.type == "can":
        db.execute(
            update(Agent)
            .where(Agent.vehicle_profile == profile.id)
            .values(vehicle_profile=None, config_version=Agent.config_version + 1)
        )
    else:
        connectors = db.scalars(select(Connector).where(Connector.mapping_profile == profile.id))
        for connector in connectors:
            connector.mapping_profile = DEFAULT_MAPPING_PROFILES[connector.kind]
            connector.config_version += 1
    db.delete(profile)
