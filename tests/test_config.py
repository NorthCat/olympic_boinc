import pytest
from pydantic import ValidationError

from olympic_boinc.config import Settings


def test_defaults(monkeypatch):
    for name in (
        "OLYMPIC_SYNC_CRON",
        "OLYMPIC_REQUEST_DELAY",
        "OLYMPIC_REQUEST_RETRIES",
        "OLYMPIC_BROWSER_PATH",
        "OLYMPIC_BROWSER_SANDBOX",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None, database_url="postgresql+asyncpg://u:p@db:5432/x")

    assert settings.sync_cron == "0 3 * * *"
    assert settings.scheduler_enabled is True
    assert settings.request_delay == 60.0
    assert settings.request_retries == 3
    assert settings.browser_path is None
    assert settings.browser_sandbox is True
    assert settings.apm_enabled is False
    assert settings.apm_server_url == "http://127.0.0.1:8200"
    assert settings.apm_service_name == "olympic-boinc"


def test_database_url_is_required(monkeypatch):
    monkeypatch.delenv("OLYMPIC_DATABASE_URL", raising=False)

    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)


def test_env_override(monkeypatch):
    monkeypatch.setenv("OLYMPIC_DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/x")
    monkeypatch.setenv("OLYMPIC_BROWSER_PATH", "/usr/bin/chromium")
    monkeypatch.setenv("OLYMPIC_BROWSER_SANDBOX", "false")
    monkeypatch.setenv("OLYMPIC_REQUEST_DELAY", "0.5")
    monkeypatch.setenv("OLYMPIC_SCHEDULER_ENABLED", "false")

    settings = Settings(_env_file=None)

    assert settings.database_url == "postgresql+asyncpg://u:p@db:5432/x"
    assert settings.browser_path == "/usr/bin/chromium"
    assert settings.browser_sandbox is False
    assert settings.request_delay == 0.5
    assert settings.scheduler_enabled is False
