from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.import_job import ImportJobStatus
from app.services import InvalidImportJobTransitionError
from app.tasks.imports import (
    UNEXPECTED_FAILURE_MESSAGE,
    process_trade_import_task,
)


class DummySession:
    def __init__(self, label: str) -> None:
        self.label = label
        self.rollback_calls = 0
        self.close_calls = 0

    def rollback(self) -> None:
        self.rollback_calls += 1

    def close(self) -> None:
        self.close_calls += 1


def test_process_trade_import_task_uses_session_storage_and_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main_session = DummySession("main")
    storage_calls: list[tuple[Path, int]] = []
    service_calls: list[tuple[DummySession, int, object]] = []
    session_calls: list[DummySession] = []
    settings = SimpleNamespace(
        upload_dir=Path("/tmp/trade-imports"),
        max_upload_size_mb=7,
    )

    def fake_session_local() -> DummySession:
        session_calls.append(main_session)
        return main_session

    class FakeStorage:
        def __init__(self, root: Path, max_size_bytes: int) -> None:
            storage_calls.append((root, max_size_bytes))

    def fake_process_trade_import_service(
        db: DummySession,
        *,
        import_job_id: int,
        storage: object,
    ) -> object:
        service_calls.append((db, import_job_id, storage))
        return object()

    monkeypatch.setattr("app.tasks.imports.SessionLocal", fake_session_local)
    monkeypatch.setattr("app.tasks.imports.settings", settings)
    monkeypatch.setattr("app.tasks.imports.LocalImportFileStorage", FakeStorage)
    monkeypatch.setattr(
        "app.tasks.imports.process_trade_import_service",
        fake_process_trade_import_service,
    )

    process_trade_import_task(41)

    assert session_calls == [main_session]
    assert storage_calls == [(settings.upload_dir, 7 * 1024 * 1024)]
    assert service_calls[0][0] is main_session
    assert service_calls[0][1] == 41
    assert isinstance(service_calls[0][2], FakeStorage)
    assert main_session.rollback_calls == 0
    assert main_session.close_calls == 1


def test_process_trade_import_task_returns_normally_for_missing_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main_session = DummySession("main")
    info_messages: list[tuple[str, int]] = []

    monkeypatch.setattr("app.tasks.imports.SessionLocal", lambda: main_session)
    monkeypatch.setattr(
        "app.tasks.imports.settings",
        SimpleNamespace(upload_dir=Path("/tmp/uploads"), max_upload_size_mb=5),
    )
    monkeypatch.setattr(
        "app.tasks.imports.LocalImportFileStorage",
        lambda root, max_size_bytes: object(),
    )
    monkeypatch.setattr(
        "app.tasks.imports.process_trade_import_service",
        lambda db, *, import_job_id, storage: None,
    )
    monkeypatch.setattr(
        "app.tasks.imports.logger",
        SimpleNamespace(
            info=lambda message, import_job_id: info_messages.append(
                (message, import_job_id)
            ),
            exception=lambda *args, **kwargs: None,
        ),
    )

    process_trade_import_task(12)

    assert info_messages == [("Trade import job %s was not found.", 12)]
    assert main_session.rollback_calls == 0
    assert main_session.close_calls == 1


@pytest.mark.parametrize(
    "current_status",
    [
        ImportJobStatus.PROCESSING,
        ImportJobStatus.COMPLETED,
        ImportJobStatus.FAILED,
    ],
)
def test_process_trade_import_task_ignores_duplicate_processing_delivery(
    monkeypatch: pytest.MonkeyPatch,
    current_status: ImportJobStatus,
) -> None:
    main_session = DummySession("main")
    info_calls: list[tuple[str, int, str]] = []

    def fake_process_trade_import_service(
        db: DummySession,
        *,
        import_job_id: int,
        storage: object,
    ) -> None:
        raise InvalidImportJobTransitionError(
            current_status=current_status,
            target_status=ImportJobStatus.PROCESSING,
        )

    monkeypatch.setattr("app.tasks.imports.SessionLocal", lambda: main_session)
    monkeypatch.setattr(
        "app.tasks.imports.settings",
        SimpleNamespace(upload_dir=Path("/tmp/uploads"), max_upload_size_mb=5),
    )
    monkeypatch.setattr(
        "app.tasks.imports.LocalImportFileStorage",
        lambda root, max_size_bytes: object(),
    )
    monkeypatch.setattr(
        "app.tasks.imports.process_trade_import_service",
        fake_process_trade_import_service,
    )
    monkeypatch.setattr(
        "app.tasks.imports.logger",
        SimpleNamespace(
            info=lambda message, import_job_id, status: info_calls.append(
                (message, import_job_id, status)
            ),
            exception=lambda *args, **kwargs: None,
        ),
    )

    process_trade_import_task(77)

    assert info_calls == [
        (
            "Ignoring duplicate or stale trade import task delivery for import job %s "
            "with current status %s.",
            77,
            current_status.value,
        )
    ]
    assert main_session.rollback_calls == 0
    assert main_session.close_calls == 1


def test_process_trade_import_task_reraises_unrelated_transition_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main_session = DummySession("main")

    def fake_process_trade_import_service(
        db: DummySession,
        *,
        import_job_id: int,
        storage: object,
    ) -> None:
        raise InvalidImportJobTransitionError(
            current_status=ImportJobStatus.PENDING,
            target_status=ImportJobStatus.COMPLETED,
        )

    monkeypatch.setattr("app.tasks.imports.SessionLocal", lambda: main_session)
    monkeypatch.setattr(
        "app.tasks.imports.settings",
        SimpleNamespace(upload_dir=Path("/tmp/uploads"), max_upload_size_mb=5),
    )
    monkeypatch.setattr(
        "app.tasks.imports.LocalImportFileStorage",
        lambda root, max_size_bytes: object(),
    )
    monkeypatch.setattr(
        "app.tasks.imports.process_trade_import_service",
        fake_process_trade_import_service,
    )

    with pytest.raises(InvalidImportJobTransitionError) as exc_info:
        process_trade_import_task(15)

    assert exc_info.value.current_status is ImportJobStatus.PENDING
    assert exc_info.value.target_status is ImportJobStatus.COMPLETED
    assert main_session.rollback_calls == 0
    assert main_session.close_calls == 1


def test_process_trade_import_task_marks_job_failed_and_reraises_original_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main_session = DummySession("main")
    failure_session = DummySession("failure")
    sessions = iter([main_session, failure_session])
    failure_calls: list[tuple[DummySession, int, str]] = []
    exception_messages: list[tuple[str, int]] = []
    original_error = RuntimeError("boom")

    monkeypatch.setattr("app.tasks.imports.SessionLocal", lambda: next(sessions))
    monkeypatch.setattr(
        "app.tasks.imports.settings",
        SimpleNamespace(upload_dir=Path("/tmp/uploads"), max_upload_size_mb=5),
    )
    monkeypatch.setattr(
        "app.tasks.imports.LocalImportFileStorage",
        lambda root, max_size_bytes: object(),
    )

    def fake_process_trade_import_service(
        db: DummySession,
        *,
        import_job_id: int,
        storage: object,
    ) -> None:
        raise original_error

    def fake_fail_import_job(
        db: DummySession,
        import_job_id: int,
        *,
        failure_message: str,
    ) -> None:
        failure_calls.append((db, import_job_id, failure_message))
        return None

    monkeypatch.setattr(
        "app.tasks.imports.process_trade_import_service",
        fake_process_trade_import_service,
    )
    monkeypatch.setattr("app.tasks.imports.fail_import_job", fake_fail_import_job)
    monkeypatch.setattr(
        "app.tasks.imports.logger",
        SimpleNamespace(
            info=lambda *args, **kwargs: None,
            exception=lambda message, import_job_id: exception_messages.append(
                (message, import_job_id)
            ),
        ),
    )

    with pytest.raises(RuntimeError) as exc_info:
        process_trade_import_task(88)

    assert exc_info.value is original_error
    assert main_session.rollback_calls == 1
    assert main_session.close_calls == 1
    assert failure_session.rollback_calls == 0
    assert failure_session.close_calls == 1
    assert failure_calls == [(failure_session, 88, UNEXPECTED_FAILURE_MESSAGE)]
    assert exception_messages == [
        ("Trade import task failed unexpectedly for import job %s.", 88)
    ]


def test_trade_import_task_keeps_original_exception_on_persist_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main_session = DummySession("main")
    failure_session = DummySession("failure")
    sessions = iter([main_session, failure_session])
    logger_calls: list[tuple[str, int]] = []
    original_error = RuntimeError("primary")
    secondary_error = RuntimeError("secondary")

    monkeypatch.setattr("app.tasks.imports.SessionLocal", lambda: next(sessions))
    monkeypatch.setattr(
        "app.tasks.imports.settings",
        SimpleNamespace(upload_dir=Path("/tmp/uploads"), max_upload_size_mb=5),
    )
    monkeypatch.setattr(
        "app.tasks.imports.LocalImportFileStorage",
        lambda root, max_size_bytes: object(),
    )
    monkeypatch.setattr(
        "app.tasks.imports.process_trade_import_service",
        lambda db, *, import_job_id, storage: (_ for _ in ()).throw(original_error),
    )

    def fake_fail_import_job(
        db: DummySession,
        import_job_id: int,
        *,
        failure_message: str,
    ) -> None:
        raise secondary_error

    monkeypatch.setattr("app.tasks.imports.fail_import_job", fake_fail_import_job)
    monkeypatch.setattr(
        "app.tasks.imports.logger",
        SimpleNamespace(
            info=lambda *args, **kwargs: None,
            exception=lambda message, import_job_id: logger_calls.append(
                (message, import_job_id)
            ),
        ),
    )

    with pytest.raises(RuntimeError) as exc_info:
        process_trade_import_task(99)

    assert exc_info.value is original_error
    assert main_session.rollback_calls == 1
    assert main_session.close_calls == 1
    assert failure_session.rollback_calls == 1
    assert failure_session.close_calls == 1
    assert logger_calls == [
        ("Trade import task failed unexpectedly for import job %s.", 99),
        (
            "Failed to persist unexpected import failure state for import job %s.",
            99,
        ),
    ]
