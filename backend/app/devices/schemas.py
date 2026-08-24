from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EnrollmentCreate(BaseModel):
    name: str = Field(default="Vehicle tracker", min_length=1, max_length=120)
    ttl_minutes: int = Field(default=30, ge=5, le=1440)


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
    online: bool
    last_seen_at: datetime | None
    last_config_sync_at: datetime | None
    config_version: int
    revoked_at: datetime | None
    created_at: datetime
