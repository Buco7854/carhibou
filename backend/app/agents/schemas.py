from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.agents.constants import (
    MAXIMUM_CADENCE_SECONDS,
    MINIMUM_CADENCE_SECONDS,
    STANDARD_CADENCE,
)

# One second is the fastest an agent is asked to work and a day is the slowest
# still worth calling telemetry. The agent enforces the same range, so a value
# outside it is rejected here rather than by an agent that then keeps its old
# configuration without saying why.
#
# The defaults are the interface's "Standard" preset, which uploads as often as
# it samples. A sample held back in the queue is a reading nobody can see, and
# the point of the data is to watch it change, so resolution rather than
# freshness is what a smaller data plan gives up.
SAMPLING_SECONDS = Field(
    default=STANDARD_CADENCE.sampling_seconds,
    ge=MINIMUM_CADENCE_SECONDS,
    le=MAXIMUM_CADENCE_SECONDS,
)
UPLOAD_SECONDS = Field(
    default=STANDARD_CADENCE.upload_seconds,
    ge=MINIMUM_CADENCE_SECONDS,
    le=MAXIMUM_CADENCE_SECONDS,
)
PARKED_SAMPLING_SECONDS = Field(
    default=STANDARD_CADENCE.parked_sampling_seconds,
    ge=MINIMUM_CADENCE_SECONDS,
    le=MAXIMUM_CADENCE_SECONDS,
)
PARKED_UPLOAD_SECONDS = Field(
    default=STANDARD_CADENCE.parked_upload_seconds,
    ge=MINIMUM_CADENCE_SECONDS,
    le=MAXIMUM_CADENCE_SECONDS,
)


class EnrollmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    implementation_id: str = Field(min_length=1, max_length=100)
    name: str = Field(default="Vehicle agent", min_length=1, max_length=120)
    vehicle_profile: str | None = Field(default=None, max_length=120)
    ttl_minutes: int = Field(default=30, ge=5, le=1440)
    sampling_seconds: int = SAMPLING_SECONDS
    upload_seconds: int = UPLOAD_SECONDS
    parked_sampling_seconds: int = PARKED_SAMPLING_SECONDS
    parked_upload_seconds: int = PARKED_UPLOAD_SECONDS


class AgentSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    vehicle_profile: str | None = Field(default=None, max_length=120)
    sampling_seconds: int = SAMPLING_SECONDS
    upload_seconds: int = UPLOAD_SECONDS
    parked_sampling_seconds: int = PARKED_SAMPLING_SECONDS
    parked_upload_seconds: int = PARKED_UPLOAD_SECONDS


class AgentSetupStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["command", "value", "link", "manual"]
    text: str = ""
    command: str = ""
    value: str = ""
    url: str = ""


class AgentImplementation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    hardware: str
    protocol_version: int
    setup_kind: Literal["command", "guided"]
    docs_url: str = ""


class EnrollmentCreated(BaseModel):
    token: str
    expires_at: datetime
    setup_steps: list[AgentSetupStep]


class EnrollRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=20, max_length=200)
    implementation_id: str = Field(min_length=1, max_length=100)
    protocol_version: int = Field(ge=1, strict=True)
    agent_version: str = Field(min_length=1, max_length=50)
    hostname: str = Field(max_length=255)
    hardware: dict[str, object] = Field(default_factory=dict)


class AgentConfig(BaseModel):
    version: int
    # Each carries "default_seconds" for a vehicle in use and "parked_seconds"
    # for one that is not; the agent decides which state it is in.
    sampling: dict[str, int]
    upload: dict[str, int]
    vehicle_profile: str | None
    vehicle_profile_definition: dict[str, object] | None = None


class EnrollResponse(BaseModel):
    agent_id: str
    vehicle_id: str
    credential: str
    config: AgentConfig


class RotateCredentialResponse(BaseModel):
    credential: str
    credential_version: int


class AgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    vehicle_id: str
    name: str
    credential_version: int
    implementation_id: str
    protocol_version: int
    agent_version: str
    compatibility: Literal["compatible", "incompatible"]
    hostname: str | None
    hardware: dict[str, object]
    vehicle_profile: str | None
    sampling_seconds: int
    upload_seconds: int
    parked_sampling_seconds: int
    parked_upload_seconds: int
    online: bool
    last_seen_at: datetime | None
    last_config_sync_at: datetime | None
    config_version: int
    revoked_at: datetime | None
    created_at: datetime


class RetiredSource(BaseModel):
    """What a retired source still holds. Oldest and newest are null when it
    reported nothing before it was retired."""

    source_id: str
    name: str
    retired_at: datetime
    samples: int
    oldest: datetime | None
    newest: datetime | None
