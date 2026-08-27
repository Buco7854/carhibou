import base64
from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import EmailStr, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_PEPPER = "development-only-session-pepper-change-me"
DEV_MASTER_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CARHIBOU_", env_file=".env", env_ignore_empty=True, extra="ignore"
    )

    environment: str = "development"
    database_url: str = "sqlite:///./carhibou.db"
    public_url: str = "http://localhost:8000"
    session_cookie_secure: bool = False
    session_cookie_name: str = "carhibou_session"
    csrf_cookie_name: str = "carhibou_csrf"
    session_ttl_hours: int = Field(default=168, ge=1, le=24 * 365)
    session_pepper: str = DEV_PEPPER
    master_key: str = DEV_MASTER_KEY
    bootstrap_admin_email: EmailStr | None = None
    bootstrap_admin_password: SecretStr | None = None
    bootstrap_admin_display_name: str = Field(default="Administrator", min_length=1, max_length=120)
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: SecretStr | None = None
    oidc_scopes: str = "openid email profile"
    oidc_group_claim: str = "groups"
    oidc_admin_group: str = ""
    oidc_auto_provision: bool = True
    oidc_display_name: str = "SSO"
    max_request_bytes: int = Field(default=32 * 1024 * 1024, ge=1024)
    media_dir: str = "./data/media"
    default_online_threshold_seconds: int = Field(default=180, ge=30)
    hook_timeout_seconds: int = Field(default=10, ge=1, le=120)
    hook_memory_mb: int = Field(default=128, ge=32, le=1024)
    hook_log_bytes: int = Field(default=64_000, ge=1024, le=1_000_000)
    worker_id: str = "worker-1"
    agent_release_dir: str = "/opt/carhibou-agent-releases"
    frontend_dir: str = ""
    log_level: str = "INFO"

    @property
    def oidc_enabled(self) -> bool:
        return bool(self.oidc_issuer.strip() and self.oidc_client_id.strip())

    @model_validator(mode="after")
    def reject_development_secrets_in_production(self) -> "Settings":
        if bool(self.bootstrap_admin_email) != bool(self.bootstrap_admin_password):
            raise ValueError("bootstrap admin email and password must be provided together")
        if (
            self.bootstrap_admin_password
            and len(self.bootstrap_admin_password.get_secret_value()) < 12
        ):
            raise ValueError("bootstrap admin password must contain at least 12 characters")
        if self.oidc_enabled and "openid" not in self.oidc_scopes.split():
            raise ValueError("OIDC scopes must include openid")
        if not self.oidc_display_name.strip():
            raise ValueError("OIDC display name must not be empty")
        if not self.oidc_group_claim.strip():
            raise ValueError("OIDC group claim must not be empty")
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
