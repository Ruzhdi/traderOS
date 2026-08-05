from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


def test_settings_include_database_url() -> None:
    get_settings.cache_clear()
    settings = get_settings()

    assert settings.database_url.startswith("postgresql+psycopg://")


def test_settings_include_celery_broker_url() -> None:
    get_settings.cache_clear()
    settings = get_settings()

    assert settings.celery_broker_url.startswith("redis://")


def test_settings_include_upload_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UPLOAD_DIR", raising=False)
    monkeypatch.delenv("MAX_UPLOAD_SIZE_MB", raising=False)

    settings = Settings(_env_file=None)

    assert settings.upload_dir == Path("uploads")
    assert settings.max_upload_size_mb == 5


@pytest.mark.parametrize("invalid_value", [0, -1])
def test_settings_reject_non_positive_max_upload_size_mb(invalid_value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, max_upload_size_mb=invalid_value)


def test_settings_include_outbox_dispatch_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.outbox_dispatch_interval_seconds == 10
    assert settings.outbox_dispatch_batch_size == 50
    assert settings.outbox_dispatch_max_attempts == 5
    assert settings.outbox_processing_timeout_seconds == 300


def test_settings_read_outbox_dispatch_interval_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OUTBOX_DISPATCH_INTERVAL_SECONDS", "30")

    settings = Settings(_env_file=None)

    assert settings.outbox_dispatch_interval_seconds == 30


@pytest.mark.parametrize(
    "field_name",
    [
        "outbox_dispatch_interval_seconds",
        "outbox_dispatch_batch_size",
        "outbox_dispatch_max_attempts",
        "outbox_processing_timeout_seconds",
    ],
)
@pytest.mark.parametrize("invalid_value", [0, -1])
def test_settings_reject_non_positive_outbox_dispatch_values(
    field_name: str, invalid_value: int
) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field_name: invalid_value})
