from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.events import TRADE_IMPORT_REQUESTED_EVENT
from app.models.import_job import ImportJob, ImportJobStatus
from app.models.outbox_event import OutboxEvent
from app.services.trade_import_submission import (
    InvalidTradeImportFilenameError,
    submit_trade_import,
)
from app.storage import LocalImportFileStorage
from tests.helpers import create_user_in_db


def test_submit_trade_import_saves_file_and_commits_job_with_outbox_event(
    db_session: Session,
    tmp_path: Path,
) -> None:
    user = create_user_in_db(db_session, "submit-success@example.com")
    storage = LocalImportFileStorage(root=tmp_path, max_size_bytes=1024)
    payload = b"symbol,side\nAAPL,long\n"

    import_job = submit_trade_import(
        db_session,
        user_id=user.id,
        original_filename=" reports\\2026\\august.csv ",
        stream=BytesIO(payload),
        storage=storage,
    )

    event = db_session.scalar(select(OutboxEvent))
    assert import_job.id is not None
    assert import_job.user_id == user.id
    assert import_job.status is ImportJobStatus.PENDING
    assert import_job.original_filename == "august.csv"
    assert event is not None
    assert event.event_type == TRADE_IMPORT_REQUESTED_EVENT
    assert event.payload == {"import_job_id": import_job.id}
    assert (tmp_path / import_job.storage_key).read_bytes() == payload


def test_submit_trade_import_uses_one_commit_for_job_and_event(
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = create_user_in_db(db_session, "submit-atomic@example.com")
    storage = LocalImportFileStorage(root=tmp_path, max_size_bytes=1024)
    commit_calls = 0
    real_commit = db_session.commit

    def record_commit() -> None:
        nonlocal commit_calls
        commit_calls += 1
        assert len(db_session.new) == 0  # both staging helpers flushed
        assert db_session.scalar(select(ImportJob)) is not None
        assert db_session.scalar(select(OutboxEvent)) is not None
        real_commit()

    monkeypatch.setattr(db_session, "commit", record_commit)

    submit_trade_import(
        db_session,
        user_id=user.id,
        original_filename="trades.csv",
        stream=BytesIO(b"symbol,side\nMSFT,long\n"),
        storage=storage,
    )

    assert commit_calls == 1


@pytest.mark.parametrize("failing_helper", ["add_import_job", "add_outbox_event"])
def test_submit_trade_import_rolls_back_and_cleans_file_on_staging_failure(
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failing_helper: str,
) -> None:
    user = create_user_in_db(db_session, f"{failing_helper}@example.com")
    storage = LocalImportFileStorage(root=tmp_path, max_size_bytes=1024)
    original_error = RuntimeError("database staging failed")
    rollback_calls = 0
    real_rollback = db_session.rollback

    def fail(*args, **kwargs):
        raise original_error

    def record_rollback() -> None:
        nonlocal rollback_calls
        rollback_calls += 1
        real_rollback()

    monkeypatch.setattr(f"app.services.trade_import_submission.{failing_helper}", fail)
    monkeypatch.setattr(db_session, "rollback", record_rollback)

    with pytest.raises(RuntimeError) as exc_info:
        submit_trade_import(
            db_session,
            user_id=user.id,
            original_filename="trades.csv",
            stream=BytesIO(b"symbol,side\nTSLA,short\n"),
            storage=storage,
        )

    assert exc_info.value is original_error
    assert rollback_calls == 1
    assert db_session.scalars(select(ImportJob)).all() == []
    assert db_session.scalars(select(OutboxEvent)).all() == []
    assert not any(path.is_file() for path in tmp_path.rglob("*"))


def test_submit_trade_import_rolls_back_and_cleans_file_on_commit_failure(
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = create_user_in_db(db_session, "commit-failure@example.com")
    storage = LocalImportFileStorage(root=tmp_path, max_size_bytes=1024)
    original_error = RuntimeError("commit failed")
    monkeypatch.setattr(
        db_session,
        "commit",
        lambda: (_ for _ in ()).throw(original_error),
    )

    with pytest.raises(RuntimeError) as exc_info:
        submit_trade_import(
            db_session,
            user_id=user.id,
            original_filename="trades.csv",
            stream=BytesIO(b"symbol,side\nNVDA,long\n"),
            storage=storage,
        )

    assert exc_info.value is original_error
    assert db_session.scalars(select(ImportJob)).all() == []
    assert db_session.scalars(select(OutboxEvent)).all() == []
    assert not any(path.is_file() for path in tmp_path.rglob("*"))


def test_submit_trade_import_rejects_null_byte_filename_before_side_effects(
    db_session: Session,
    tmp_path: Path,
) -> None:
    user = create_user_in_db(db_session, "invalid-filename@example.com")
    storage = LocalImportFileStorage(root=tmp_path, max_size_bytes=1024)

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
        )

    assert db_session.scalars(select(ImportJob)).all() == []
    assert not any(path.is_file() for path in tmp_path.rglob("*"))


def test_submit_trade_import_preserves_db_error_when_file_cleanup_fails(
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = create_user_in_db(db_session, "cleanup-failure@example.com")
    storage = LocalImportFileStorage(root=tmp_path, max_size_bytes=1024)
    original_error = RuntimeError("database failed")
    log_calls: list[tuple[str, tuple[object, ...]]] = []

    monkeypatch.setattr(
        "app.services.trade_import_submission.add_import_job",
        lambda *args, **kwargs: (_ for _ in ()).throw(original_error),
    )
    monkeypatch.setattr(storage, "delete", lambda key: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(
        "app.services.trade_import_submission.logger",
        SimpleNamespace(
            exception=lambda message, *args: log_calls.append((message, args))
        ),
    )

    with pytest.raises(RuntimeError) as exc_info:
        submit_trade_import(
            db_session,
            user_id=user.id,
            original_filename="trades.csv",
            stream=BytesIO(b"symbol,side\nAMD,long\n"),
            storage=storage,
        )

    assert exc_info.value is original_error
    assert log_calls[0][0] == (
        "Failed to delete stored trade import file %s during cleanup."
    )
