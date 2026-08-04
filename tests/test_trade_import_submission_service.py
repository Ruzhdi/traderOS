from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from app.models.import_job import ImportJobStatus
from app.repositories.import_job import list_import_jobs_by_user
from app.services.trade_import_submission import (
    InvalidTradeImportFilenameError,
    TradeImportEnqueueError,
    submit_trade_import,
)
from app.storage import LocalImportFileStorage
from tests.helpers import create_user_in_db


def test_submit_trade_import_saves_file_creates_job_and_enqueues(
    db_session: Session,
    tmp_path: Path,
) -> None:
    user = create_user_in_db(db_session, "submit-success@example.com")
    storage = LocalImportFileStorage(root=tmp_path, max_size_bytes=1024)
    enqueue_calls: list[int] = []
    payload = b"symbol,side\nAAPL,long\n"

    import_job = submit_trade_import(
        db_session,
        user_id=user.id,
        original_filename=" reports\\2026\\august.csv ",
        stream=BytesIO(payload),
        storage=storage,
        enqueue=lambda import_job_id: enqueue_calls.append(import_job_id),
    )

    assert import_job.id is not None
    assert import_job.user_id == user.id
    assert import_job.status is ImportJobStatus.PENDING
    assert import_job.original_filename == "august.csv"
    assert enqueue_calls == [import_job.id]
    assert (tmp_path / import_job.storage_key).read_bytes() == payload


def test_submit_trade_import_enqueues_only_after_job_commit(
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = create_user_in_db(db_session, "submit-ordering@example.com")
    storage = LocalImportFileStorage(root=tmp_path, max_size_bytes=1024)
    events: list[str] = []
    real_commit = db_session.commit

    def record_commit() -> None:
        events.append("commit")
        real_commit()

    monkeypatch.setattr(db_session, "commit", record_commit)

    def enqueue(import_job_id: int) -> None:
        events.append(f"enqueue:{import_job_id}")

    import_job = submit_trade_import(
        db_session,
        user_id=user.id,
        original_filename="trades.csv",
        stream=BytesIO(b"symbol,side\nMSFT,long\n"),
        storage=storage,
        enqueue=enqueue,
    )

    assert events == ["commit", f"enqueue:{import_job.id}"]


def test_submit_trade_import_cleans_up_file_and_skips_enqueue_on_db_failure(
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = create_user_in_db(db_session, "submit-db-failure@example.com")
    storage = LocalImportFileStorage(root=tmp_path, max_size_bytes=1024)
    enqueue_calls: list[int] = []
    original_error = RuntimeError("database write failed")

    def fake_create_import_job(*args, **kwargs):
        raise original_error

    monkeypatch.setattr(
        "app.services.trade_import_submission.create_import_job",
        fake_create_import_job,
    )

    with pytest.raises(RuntimeError) as exc_info:
        submit_trade_import(
            db_session,
            user_id=user.id,
            original_filename="trades.csv",
            stream=BytesIO(b"symbol,side\nTSLA,short\n"),
            storage=storage,
            enqueue=lambda import_job_id: enqueue_calls.append(import_job_id),
        )

    assert exc_info.value is original_error
    assert enqueue_calls == []
    assert list_import_jobs_by_user(db_session, user.id) == []
    assert not any(path.is_file() for path in tmp_path.rglob("*"))


def test_submit_trade_import_marks_failed_cleans_file_and_raises_safe_enqueue_error(
    db_session: Session,
    tmp_path: Path,
) -> None:
    user = create_user_in_db(db_session, "submit-enqueue-failure@example.com")
    storage = LocalImportFileStorage(root=tmp_path, max_size_bytes=1024)
    broker_error = RuntimeError("redis://user:secret@broker:6379/0 unavailable")

    def failing_enqueue(_: int) -> None:
        raise broker_error

    with pytest.raises(TradeImportEnqueueError) as exc_info:
        submit_trade_import(
            db_session,
            user_id=user.id,
            original_filename="trades.csv",
            stream=BytesIO(b"symbol,side\nNVDA,long\n"),
            storage=storage,
            enqueue=failing_enqueue,
        )

    jobs = list_import_jobs_by_user(db_session, user.id)
    assert len(jobs) == 1

    import_job = jobs[0]
    assert import_job.status is ImportJobStatus.FAILED
    assert import_job.failure_message == "Import could not be queued for processing."
    assert (tmp_path / import_job.storage_key).exists() is False
    assert str(exc_info.value) == "Import could not be queued for processing."
    assert "redis://" not in str(exc_info.value)
    assert exc_info.value.__cause__ is broker_error


def test_submit_trade_import_rejects_null_byte_filename_before_side_effects(
    db_session: Session,
    tmp_path: Path,
) -> None:
    user = create_user_in_db(db_session, "submit-invalid-filename@example.com")
    storage = LocalImportFileStorage(root=tmp_path, max_size_bytes=1024)
    enqueue_calls: list[int] = []

    with pytest.raises(
        InvalidTradeImportFilenameError,
        match="Import filename is invalid.",
    ):
        submit_trade_import(
            db_session,
            user_id=user.id,
            original_filename="bad\x00name.csv",
            stream=BytesIO(b"symbol,side\nAAPL,long\n"),
            storage=storage,
            enqueue=lambda import_job_id: enqueue_calls.append(import_job_id),
        )

    assert enqueue_calls == []
    assert list_import_jobs_by_user(db_session, user.id) == []
    assert not any(path.is_file() for path in tmp_path.rglob("*"))


def test_submit_trade_import_preserves_enqueue_error_when_cleanup_steps_fail(
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = create_user_in_db(db_session, "submit-cleanup-failure@example.com")
    storage = LocalImportFileStorage(root=tmp_path, max_size_bytes=1024)
    log_calls: list[tuple[str, tuple[object, ...]]] = []
    broker_error = RuntimeError("broker unavailable")

    def failing_enqueue(_: int) -> None:
        raise broker_error

    def fake_fail_import_job(*args, **kwargs):
        raise RuntimeError("failed to persist failed state")

    def fake_delete(_: str) -> bool:
        raise OSError("failed to delete stored file")

    monkeypatch.setattr(
        "app.services.trade_import_submission.fail_import_job",
        fake_fail_import_job,
    )
    monkeypatch.setattr(storage, "delete", fake_delete)
    monkeypatch.setattr(
        "app.services.trade_import_submission.logger",
        SimpleNamespace(
            exception=lambda message, *args: log_calls.append((message, args))
        ),
    )

    with pytest.raises(TradeImportEnqueueError) as exc_info:
        submit_trade_import(
            db_session,
            user_id=user.id,
            original_filename="trades.csv",
            stream=BytesIO(b"symbol,side\nAMD,long\n"),
            storage=storage,
            enqueue=failing_enqueue,
        )

    assert exc_info.value.__cause__ is broker_error
    assert len(log_calls) == 2
    assert log_calls[0][0] == (
        "Failed to mark trade import job %s as failed after enqueue error."
    )
    assert log_calls[1][0] == (
        "Failed to delete stored trade import file %s during cleanup."
    )
