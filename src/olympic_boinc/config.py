from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OLYMPIC_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )

    database_url: str  # required, e.g. postgresql+asyncpg://user:password@host:5432/olympic_boinc
    sync_cron: str = "0 3 * * *"
    scheduler_enabled: bool = True
    # Run immediately after startup as well as on schedule, if the scheduler is enabled.
    sync_on_startup: bool = False
    # Load the freshest pages first; leave remaining history for later runs.
    sync_max_challenges: int = Field(100, ge=0)
    # Scheduler runs and requested URLs; relative to the working directory.
    sync_log_file: Path = Path("logs/sync.log")

    request_delay: float = 60.0  # BoincStats shows a captcha when pages are requested too often
    request_retries: int = 3
    browser_path: str | None = None  # Chrome/Chromium executable; None lets nodriver find it
    # Chromium without an AppArmor profile (e.g. not from a .deb) needs False.
    browser_sandbox: bool = True

    apm_enabled: bool = False
    apm_server_url: str = "http://127.0.0.1:8200"
    apm_service_name: str = Field("olympic-boinc", pattern=r"^[a-zA-Z0-9 _-]+$")
    apm_environment: str = "local"
    apm_secret_token: SecretStr | None = None
    apm_transaction_sample_rate: float = Field(1.0, ge=0, le=1, allow_inf_nan=False)

    @field_validator("apm_service_name")
    @classmethod
    def validate_apm_service_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("APM service name must not be blank")

        return value

    @field_validator("apm_server_url")
    @classmethod
    def validate_apm_server_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError("APM server URL must be HTTP(S) without credentials")

        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
