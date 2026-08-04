from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "traderos",
    broker=settings.celery_broker_url,
    include=["app.tasks.system", "app.tasks.imports"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
)
