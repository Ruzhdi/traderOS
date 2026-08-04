from app.core.config import get_settings
from app.tasks.imports import process_trade_import_task
from app.tasks.system import worker_ping
from app.worker.celery_app import celery_app


def test_celery_app_uses_configured_broker_url() -> None:
    settings = get_settings()

    assert celery_app.conf.broker_url == settings.celery_broker_url


def test_celery_app_uses_json_only_serialization() -> None:
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.result_serializer == "json"
    assert celery_app.conf.accept_content == ["json"]


def test_celery_app_uses_utc_and_ignores_results() -> None:
    assert celery_app.conf.timezone == "UTC"
    assert celery_app.conf.enable_utc is True
    assert celery_app.conf.task_ignore_result is True
    assert celery_app.conf.broker_connection_retry_on_startup is True


def test_worker_ping_task_has_stable_name() -> None:
    assert worker_ping.name == "app.tasks.system.worker_ping"


def test_process_trade_import_task_has_stable_name() -> None:
    assert process_trade_import_task.name == "app.tasks.imports.process_trade_import"


def test_celery_app_includes_import_tasks_module() -> None:
    assert "app.tasks.system" in celery_app.conf.include
    assert "app.tasks.imports" in celery_app.conf.include


def test_worker_ping_task_body_returns_pong() -> None:
    assert worker_ping() == "pong"


def test_celery_app_registers_process_trade_import_task() -> None:
    registered_task = celery_app.tasks["app.tasks.imports.process_trade_import"]

    assert registered_task.name == process_trade_import_task.name
