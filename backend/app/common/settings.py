import base64
from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_PEPPER = "development-only-session-pepper-change-me"
DEV_MASTER_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VEHINODE_", env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "sqlite:///./vehinode.db"
    public_url: str = "http://localhost:8000"
    session_cookie_secure: bool = False
    session_cookie_name: str = "vehinode_session"
    csrf_cookie_name: str = "vehinode_csrf"
    session_ttl_hours: int = Field(default=168, ge=1, le=24 * 365)
    session_pepper: str = DEV_PEPPER
    master_key: str = DEV_MASTER_KEY
    registration_enabled: bool = True
    max_request_bytes: int = Field(default=2_000_000, ge=1024)
    default_online_threshold_seconds: int = Field(default=180, ge=30)
    hook_timeout_seconds: int = Field(default=10, ge=1, le=120)
    hook_memory_mb: int = Field(default=128, ge=32, le=1024)
    hook_log_bytes: int = Field(default=64_000, ge=1024, le=1_000_000)
    worker_id: str = "worker-1"
    agent_release_dir: str = "/opt/vehinode-agent-releases"
    frontend_dir: str = ""
    log_level: str = "INFO"

    @model_validator(mode="after")
    def reject_development_secrets_in_production(self) -> "Settings":
        try:
            master_key = base64.urlsafe_b64decode(self.master_key.encode())
        except Exception as exc:
            raise ValueError("master key must be a URL-safe base64 key") from exc
        if len(master_key) != 32:
            raise ValueError("master key must decode to exactly 32 bytes")
        parsed_url = urlsplit(self.public_url)
        if (
            parsed_url.scheme not in {"http", "https"}
            or not parsed_url.hostname
            or parsed_url.username
            or parsed_url.password
            or parsed_url.path not in {"", "/"}
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise ValueError("public URL must be an HTTP(S) origin without credentials or a path")
        if self.environment == "production":
            if self.session_pepper == DEV_PEPPER or self.master_key == DEV_MASTER_KEY:
                raise ValueError("production requires unique session pepper and master key")
            if len(self.session_pepper) < 32:
                raise ValueError("production session pepper must contain at least 32 characters")
            if not self.session_cookie_secure:
                raise ValueError("production requires secure session cookies")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
