from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# One second is the fastest a tracker is asked to work and a day is the slowest
# still worth calling telemetry. The agent enforces the same range, so a value
# outside it is rejected here rather than by a tracker that then keeps its old
# configuration without saying why.
#
# The defaults are the interface's "Standard" preset, which uploads as often as
# it samples. A sample held back in the queue is a reading nobody can see, and
# the point of the data is to watch it change, so resolution rather than
# freshness is what a smaller data plan gives up.
SAMPLING_SECONDS = Field(default=5, ge=1, le=86400)
UPLOAD_SECONDS = Field(default=5, ge=1, le=86400)
PARKED_SAMPLING_SECONDS = Field(default=300, ge=1, le=86400)
PARKED_UPLOAD_SECONDS = Field(default=300, ge=1, le=86400)


class EnrollmentCreate(BaseModel):
    name: str = Field(default="Vehicle tracker", min_length=1, max_length=120)
    ttl_minutes: int = Field(default=30, ge=5, le=1440)
    sampling_seconds: int = SAMPLING_SECONDS
    upload_seconds: int = UPLOAD_SECONDS
    parked_sampling_seconds: int = PARKED_SAMPLING_SECONDS
    parked_upload_seconds: int = PARKED_UPLOAD_SECONDS


class DeviceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    sampling_seconds: int = SAMPLING_SECONDS
    upload_seconds: int = UPLOAD_SECONDS
    parked_sampling_seconds: int = PARKED_SAMPLING_SECONDS
    parked_upload_seconds: int = PARKED_UPLOAD_SECONDS


class EnrollmentCreated(BaseModel):
    token: str
    expires_at: datetime
    install_command: str


class EnrollRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    agent_version: str = Field(max_length=50)
    hostname: str = Field(max_length=255)
    hardware: dict[str, object] = Field(default_factory=dict)


class DeviceConfig(BaseModel):
    version: int
    # Each carries "default_seconds" for a vehicle in use and "parked_seconds"
    # for one that is not; the tracker decides which state it is in.
    sampling: dict[str, int]
    upload: dict[str, int]
    vehicle_profile: str | None
    vehicle_profile_definition: dict[str, object] | None = None


class EnrollResponse(BaseModel):
    device_id: str
    vehicle_id: str
    credential: str
    config: DeviceConfig


class RotateCredentialResponse(BaseModel):
    credential: str
    credential_version: int


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    vehicle_id: str
    name: str
    credential_version: int
    agent_version: str | None
    hostname: str | None
    hardware: dict[str, object]
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
