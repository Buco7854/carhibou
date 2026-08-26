from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# One second is the fastest a tracker is asked to work and a day is the slowest
# still worth calling telemetry. The agent enforces the same range, so a value
# outside it is rejected here rather than by a tracker that then keeps its old
# configuration without saying why.
#
# The defaults are the interface's "Standard" preset. A minute between uploads
# rather than thirty seconds halves the request count at no cost in data, since
# samples are queued until they are acknowledged either way.
SAMPLING_SECONDS = Field(default=5, ge=1, le=86400)
UPLOAD_SECONDS = Field(default=60, ge=1, le=86400)


class EnrollmentCreate(BaseModel):
    name: str = Field(default="Vehicle tracker", min_length=1, max_length=120)
    ttl_minutes: int = Field(default=30, ge=5, le=1440)
    sampling_seconds: int = SAMPLING_SECONDS
    upload_seconds: int = UPLOAD_SECONDS


class DeviceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    sampling_seconds: int = SAMPLING_SECONDS
    upload_seconds: int = UPLOAD_SECONDS


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
    online: bool
    last_seen_at: datetime | None
    last_config_sync_at: datetime | None
    config_version: int
    revoked_at: datetime | None
    created_at: datetime
