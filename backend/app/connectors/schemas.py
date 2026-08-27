import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError


class MqttConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1, max_length=253)
    port: int = Field(default=1883, ge=1, le=65535)
    tls: bool = False
    tls_accept_invalid_certs: bool = False
    username: str = Field(default="", max_length=255)
    namespace: str = Field(default="", max_length=255)
    car_id: int = Field(default=1, ge=1)
    sample_seconds: int = Field(default=10, ge=1, le=3600)

    @field_validator("host")
    @classmethod
    def valid_host(cls, value: str) -> str:
        host = value.strip()
        if (
            host != value
            or "://" in host
            or any(char.isspace() for char in host)
            or any(char in host for char in "/?#@")
            or not re.fullmatch(
                r"(?:[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?|\[[0-9A-Fa-f:]+\])",
                host,
            )
        ):
            raise PydanticCustomError(
                "invalid_host", "host must be a hostname or IP address without a scheme or path"
            )
        return host

    @field_validator("namespace")
    @classmethod
    def valid_namespace(cls, value: str) -> str:
        namespace = value.strip().strip("/")
        if any(char.isspace() for char in namespace) or "#" in namespace or "+" in namespace:
            raise PydanticCustomError(
                "invalid_namespace", "namespace must contain MQTT topic segments only"
            )
        return namespace

    @model_validator(mode="after")
    def valid_tls_options(self) -> "MqttConfig":
        if self.tls_accept_invalid_certs and not self.tls:
            raise PydanticCustomError(
                "invalid_tls_options", "tls_accept_invalid_certs requires tls"
            )
        return self


class ConnectorCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["teslamate.mqtt"]
    name: str = Field(min_length=1, max_length=120)
    config: MqttConfig
    password: str | None = Field(default=None, max_length=10000)


class ConnectorUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    enabled: bool
    config: MqttConfig
    password: str | None = Field(default=None, max_length=10000)


class ConnectorKindResponse(BaseModel):
    id: str
    name: str
    description: str
    docs_url: str


class ConnectorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    vehicle_id: str
    name: str
    kind: str
    enabled: bool
    config: MqttConfig
    masked: str
    config_version: int
    status: Literal["disabled", "connecting", "connected", "error"]
    last_connected_at: datetime | None
    last_message_at: datetime | None
    last_sample_at: datetime | None
    last_error: str
    created_at: datetime
    updated_at: datetime
