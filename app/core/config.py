from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "TraderOS API"
    app_env: str = "local"
    database_url: str = "postgresql+psycopg://traderos:traderos@localhost:5432/traderos"
    celery_broker_url: str = "redis://localhost:6379/0"
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    upload_dir: Path = Path("uploads")
    max_upload_size_mb: int = Field(default=5, gt=0)
    outbox_dispatch_interval_seconds: int = Field(default=10, gt=0)
    outbox_dispatch_batch_size: int = Field(default=50, gt=0)
    outbox_dispatch_max_attempts: int = Field(default=5, gt=0)
    outbox_processing_timeout_seconds: int = Field(default=300, gt=0)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
