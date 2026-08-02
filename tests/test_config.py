from app.core.config import get_settings


def test_settings_include_database_url() -> None:
    settings = get_settings()

    assert settings.database_url.startswith("postgresql+psycopg://")


def test_settings_include_celery_broker_url() -> None:
    settings = get_settings()

    assert settings.celery_broker_url.startswith("redis://")
