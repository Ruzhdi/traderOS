from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.import_job import ImportJobStatus
from app.models.trade import Trade
from app.repositories.import_job import create_import_job, get_import_job_by_id
from app.services.import_job import (
    InvalidImportJobTransitionError,
    complete_import_job,
    fail_import_job,
    start_import_job,
)
from app.services.trade_import import process_trade_import
from app.storage.import_files import LocalImportFileStorage
from tests.helpers import create_user_in_db, normalize_to_utc


def test_process_trade_import_uses_storage_key_not_original_filename(
    db_session: Session,
    tmp_path: Path,
) -> None:
    user = create_user_in_db(db_session, "import-valid@example.com")
    storage = LocalImportFileStorage(tmp_path, max_size_bytes=1024 * 1024)
    storage_key = "imports/1/valid.csv"
    _write_storage_text(
        tmp_path,
        storage_key,
        "symbol,side,entry_price,quantity,opened_at\n"
        "AAPL,long,192.50,10,2026-07-16T09:30:00Z\n",
    )
    import_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="../../not-the-real-path.csv",
        storage_key=storage_key,
    )

    completed_job = process_trade_import(
        db_session,
        import_job_id=import_job.id,
        storage=storage,
    )

    assert completed_job is not None
    assert completed_job.status is ImportJobStatus.COMPLETED
    assert completed_job.total_rows == 1
    assert completed_job.imported_rows == 1
    assert completed_job.rejected_rows == 0
    assert completed_job.started_at is not None
    assert completed_job.completed_at is not None

    trades = _list_trades(db_session)
    assert len(trades) == 1
    assert trades[0].user_id == user.id
    assert trades[0].symbol == "AAPL"
    assert trades[0].side == "long"
    assert trades[0].entry_price == Decimal("192.50")
    assert trades[0].quantity == Decimal("10")
    assert normalize_to_utc(trades[0].opened_at) == datetime(
        2026,
        7,
        16,
        9,
        30,
        tzinfo=UTC,
    )


def test_process_trade_import_imports_multiple_rows(
    db_session: Session,
    tmp_path: Path,
) -> None:
    user = create_user_in_db(db_session, "import-multi@example.com")
    other_user = create_user_in_db(db_session, "other-import@example.com")
    storage = LocalImportFileStorage(tmp_path, max_size_bytes=1024 * 1024)
    storage_key = "imports/2/multi.csv"
    _write_storage_text(
        tmp_path,
        storage_key,
        "symbol,side,entry_price,exit_price,quantity,opened_at,closed_at,pnl,notes\n"
        "NVDA,long,130.00,132.50,4,2026-07-16T13:15:00Z,"
        "2026-07-16T14:00:00Z,10.00,Later trade\n"
        "TSLA,short,250.00,,2,2026-07-16T10:00:00Z,,,Opening position\n",
    )
    import_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="multi.csv",
        storage_key=storage_key,
    )

    completed_job = process_trade_import(
        db_session,
        import_job_id=import_job.id,
        storage=storage,
    )

    assert completed_job is not None
    assert completed_job.total_rows == 2
    assert completed_job.imported_rows == 2
    assert completed_job.rejected_rows == 0

    trades = _list_trades(db_session)
    assert len(trades) == 2
    assert all(trade.user_id == user.id for trade in trades)
    assert all(trade.user_id != other_user.id for trade in trades)
    assert {trade.symbol for trade in trades} == {"NVDA", "TSLA"}


def test_process_trade_import_accepts_required_only_columns(
    db_session: Session,
    tmp_path: Path,
) -> None:
    user = create_user_in_db(db_session, "required-only@example.com")
    storage = LocalImportFileStorage(tmp_path, max_size_bytes=1024 * 1024)
    storage_key = "imports/3/required-only.csv"
    _write_storage_text(
        tmp_path,
        storage_key,
        "symbol,side,entry_price,quantity,opened_at\n"
        "MSFT,short,430.00,5,2026-07-16T11:00:00Z\n",
    )
    import_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="required-only.csv",
        storage_key=storage_key,
    )

    completed_job = process_trade_import(
        db_session,
        import_job_id=import_job.id,
        storage=storage,
    )

    assert completed_job is not None
    assert completed_job.total_rows == 1
    assert completed_job.imported_rows == 1
    assert completed_job.rejected_rows == 0

    trade = _list_trades(db_session)[0]
    assert trade.exit_price is None
    assert trade.closed_at is None
    assert trade.pnl is None
    assert trade.notes is None


def test_process_trade_import_completes_header_only_csv(
    db_session: Session,
    tmp_path: Path,
) -> None:
    user = create_user_in_db(db_session, "header-only@example.com")
    storage = LocalImportFileStorage(tmp_path, max_size_bytes=1024 * 1024)
    storage_key = "imports/4/header-only.csv"
    _write_storage_text(
        tmp_path,
        storage_key,
        "symbol,side,entry_price,quantity,opened_at\n",
    )
    import_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="header-only.csv",
        storage_key=storage_key,
    )

    completed_job = process_trade_import(
        db_session,
        import_job_id=import_job.id,
        storage=storage,
    )

    assert completed_job is not None
    assert completed_job.status is ImportJobStatus.COMPLETED
    assert completed_job.total_rows == 0
    assert completed_job.imported_rows == 0
    assert completed_job.rejected_rows == 0
    assert _list_trades(db_session) == []


def test_process_trade_import_counts_mixed_valid_and_invalid_rows(
    db_session: Session,
    tmp_path: Path,
) -> None:
    user = create_user_in_db(db_session, "mixed@example.com")
    storage = LocalImportFileStorage(tmp_path, max_size_bytes=1024 * 1024)
    storage_key = "imports/5/mixed.csv"
    _write_storage_text(
        tmp_path,
        storage_key,
        "symbol,side,entry_price,quantity,opened_at\n"
        "AAPL,long,192.50,10,2026-07-16T09:30:00Z\n"
        "TSLA,long,-1,1,2026-07-16T10:00:00Z\n"
        "NVDA,short,130.00,2,2026-07-16T11:00:00Z\n",
    )
    import_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="mixed.csv",
        storage_key=storage_key,
    )

    completed_job = process_trade_import(
        db_session,
        import_job_id=import_job.id,
        storage=storage,
    )

    assert completed_job is not None
    assert completed_job.total_rows == 3
    assert completed_job.imported_rows == 2
    assert completed_job.rejected_rows == 1
    assert [trade.symbol for trade in _list_trades(db_session)] == ["AAPL", "NVDA"]


def test_process_trade_import_completes_all_invalid_rows_without_trades(
    db_session: Session,
    tmp_path: Path,
) -> None:
    user = create_user_in_db(db_session, "all-invalid@example.com")
    storage = LocalImportFileStorage(tmp_path, max_size_bytes=1024 * 1024)
    storage_key = "imports/6/all-invalid.csv"
    _write_storage_text(
        tmp_path,
        storage_key,
        "symbol,side,entry_price,quantity,opened_at\n"
        ",long,192.50,10,2026-07-16T09:30:00Z\n"
        "TSLA,long,-1,1,2026-07-16T10:00:00Z\n",
    )
    import_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="all-invalid.csv",
        storage_key=storage_key,
    )

    completed_job = process_trade_import(
        db_session,
        import_job_id=import_job.id,
        storage=storage,
    )

    assert completed_job is not None
    assert completed_job.status is ImportJobStatus.COMPLETED
    assert completed_job.total_rows == 2
    assert completed_job.imported_rows == 0
    assert completed_job.rejected_rows == 2
    assert _list_trades(db_session) == []


def test_process_trade_import_ignores_blank_rows_in_counters(
    db_session: Session,
    tmp_path: Path,
) -> None:
    user = create_user_in_db(db_session, "blank-rows@example.com")
    storage = LocalImportFileStorage(tmp_path, max_size_bytes=1024 * 1024)
    storage_key = "imports/7/blank-rows.csv"
    _write_storage_text(
        tmp_path,
        storage_key,
        "symbol,side,entry_price,quantity,opened_at\n"
        "\n"
        "AAPL,long,192.50,10,2026-07-16T09:30:00Z\n"
        ",,,,\n"
        "MSFT,short,430.00,5,2026-07-16T11:00:00Z\n"
        "\n",
    )
    import_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="blank-rows.csv",
        storage_key=storage_key,
    )

    completed_job = process_trade_import(
        db_session,
        import_job_id=import_job.id,
        storage=storage,
    )

    assert completed_job is not None
    assert completed_job.total_rows == 2
    assert completed_job.imported_rows == 2
    assert completed_job.rejected_rows == 0
    assert len(_list_trades(db_session)) == 2


def test_process_trade_import_fails_for_missing_file_and_preserves_started_at(
    db_session: Session,
    tmp_path: Path,
) -> None:
    user = create_user_in_db(db_session, "missing-file@example.com")
    storage = LocalImportFileStorage(tmp_path, max_size_bytes=1024 * 1024)
    import_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="missing.csv",
        storage_key="imports/8/missing.csv",
    )

    failed_job = process_trade_import(
        db_session,
        import_job_id=import_job.id,
        storage=storage,
    )

    assert failed_job is not None
    assert failed_job.status is ImportJobStatus.FAILED
    assert failed_job.failure_message == "Import file was not found."
    assert failed_job.started_at is not None
    assert failed_job.completed_at is not None
    assert _list_trades(db_session) == []


def test_process_trade_import_fails_for_invalid_storage_key(
    db_session: Session,
    tmp_path: Path,
) -> None:
    user = create_user_in_db(db_session, "invalid-key@example.com")
    storage = LocalImportFileStorage(tmp_path, max_size_bytes=1024 * 1024)
    import_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="invalid-key.csv",
        storage_key="../escape.csv",
    )

    failed_job = process_trade_import(
        db_session,
        import_job_id=import_job.id,
        storage=storage,
    )

    assert failed_job is not None
    assert failed_job.status is ImportJobStatus.FAILED
    assert failed_job.failure_message == "Import file reference is invalid."
    assert failed_job.started_at is not None
    assert _list_trades(db_session) == []


def test_process_trade_import_fails_for_invalid_header(
    db_session: Session,
    tmp_path: Path,
) -> None:
    user = create_user_in_db(db_session, "invalid-header@example.com")
    storage = LocalImportFileStorage(tmp_path, max_size_bytes=1024 * 1024)
    storage_key = "imports/9/invalid-header.csv"
    _write_storage_text(
        tmp_path,
        storage_key,
        "ticker,side,entry_price,quantity,opened_at\n"
        "AAPL,long,192.50,10,2026-07-16T09:30:00Z\n",
    )
    import_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="invalid-header.csv",
        storage_key=storage_key,
    )

    failed_job = process_trade_import(
        db_session,
        import_job_id=import_job.id,
        storage=storage,
    )

    assert failed_job is not None
    assert failed_job.status is ImportJobStatus.FAILED
    assert (
        failed_job.failure_message
        == "Missing required headers: symbol; Unexpected headers: ticker."
    )
    assert failed_job.started_at is not None
    assert _list_trades(db_session) == []


def test_process_trade_import_fails_for_invalid_utf8(
    db_session: Session,
    tmp_path: Path,
) -> None:
    user = create_user_in_db(db_session, "invalid-utf8@example.com")
    storage = LocalImportFileStorage(tmp_path, max_size_bytes=1024 * 1024)
    storage_key = "imports/10/invalid-utf8.csv"
    _write_storage_bytes(tmp_path, storage_key, b"\xff\xfe\x00bad")
    import_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="invalid-utf8.csv",
        storage_key=storage_key,
    )

    failed_job = process_trade_import(
        db_session,
        import_job_id=import_job.id,
        storage=storage,
    )

    assert failed_job is not None
    assert failed_job.status is ImportJobStatus.FAILED
    assert failed_job.failure_message == "Import file must be valid UTF-8 CSV text."
    assert _list_trades(db_session) == []


def test_process_trade_import_returns_none_for_missing_job(
    db_session: Session,
    tmp_path: Path,
) -> None:
    storage = LocalImportFileStorage(tmp_path, max_size_bytes=1024 * 1024)

    result = process_trade_import(
        db_session,
        import_job_id=999999,
        storage=storage,
    )

    assert result is None


@pytest.mark.parametrize(
    "terminal_status",
    [ImportJobStatus.COMPLETED, ImportJobStatus.FAILED],
)
def test_process_trade_import_rejects_terminal_jobs(
    db_session: Session,
    tmp_path: Path,
    terminal_status: ImportJobStatus,
) -> None:
    user = create_user_in_db(db_session, f"{terminal_status.value}@example.com")
    storage = LocalImportFileStorage(tmp_path, max_size_bytes=1024 * 1024)
    storage_key = f"imports/11/{terminal_status.value}.csv"
    _write_storage_text(
        tmp_path,
        storage_key,
        "symbol,side,entry_price,quantity,opened_at\n"
        "AAPL,long,192.50,10,2026-07-16T09:30:00Z\n",
    )
    import_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename=f"{terminal_status.value}.csv",
        storage_key=storage_key,
    )
    started_job = start_import_job(db_session, import_job.id)
    assert started_job is not None

    if terminal_status is ImportJobStatus.COMPLETED:
        complete_import_job(
            db_session,
            import_job.id,
            total_rows=0,
            imported_rows=0,
            rejected_rows=0,
        )
    else:
        fail_import_job(
            db_session,
            import_job.id,
            failure_message="Already failed.",
        )

    with pytest.raises(InvalidImportJobTransitionError) as exc_info:
        process_trade_import(
            db_session,
            import_job_id=import_job.id,
            storage=storage,
        )

    assert exc_info.value.current_status is terminal_status
    assert exc_info.value.target_status is ImportJobStatus.PROCESSING


def test_process_trade_import_propagates_unexpected_flush_failure(
    db_session: Session,
    tmp_path: Path,
) -> None:
    user = create_user_in_db(db_session, "flush-failure@example.com")
    storage = LocalImportFileStorage(tmp_path, max_size_bytes=1024 * 1024)
    storage_key = "imports/12/flush-failure.csv"
    _write_storage_text(
        tmp_path,
        storage_key,
        "symbol,side,entry_price,quantity,opened_at\n"
        "AAPL,long,192.50,10,2026-07-16T09:30:00Z\n",
    )
    import_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="flush-failure.csv",
        storage_key=storage_key,
    )
    original_flush = db_session.flush
    flush_calls = 0

    def failing_flush(*args: object, **kwargs: object) -> None:
        nonlocal flush_calls
        flush_calls += 1
        if flush_calls == 1:
            original_flush(*args, **kwargs)
            return
        raise SQLAlchemyError("flush failed")

    db_session.flush = failing_flush
    try:
        with pytest.raises(SQLAlchemyError, match="flush failed"):
            process_trade_import(
                db_session,
                import_job_id=import_job.id,
                storage=storage,
            )
    finally:
        db_session.flush = original_flush

    assert _list_trades(db_session) == []
    persisted_job = get_import_job_by_id(db_session, import_job.id)
    assert persisted_job is not None
    assert persisted_job.status is ImportJobStatus.PROCESSING


def test_process_trade_import_rolls_back_atomic_final_transaction(
    db_session: Session,
    tmp_path: Path,
) -> None:
    user = create_user_in_db(db_session, "atomic@example.com")
    storage = LocalImportFileStorage(tmp_path, max_size_bytes=1024 * 1024)
    storage_key = "imports/13/atomic.csv"
    _write_storage_text(
        tmp_path,
        storage_key,
        "symbol,side,entry_price,quantity,opened_at\n"
        "AAPL,long,192.50,10,2026-07-16T09:30:00Z\n",
    )
    import_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="atomic.csv",
        storage_key=storage_key,
    )
    original_commit = db_session.commit
    commit_calls = 0

    def commit_once_then_fail() -> None:
        nonlocal commit_calls
        commit_calls += 1
        if commit_calls == 1:
            original_commit()
            return
        raise SQLAlchemyError("commit failed")

    db_session.commit = commit_once_then_fail
    try:
        with pytest.raises(SQLAlchemyError, match="commit failed"):
            process_trade_import(
                db_session,
                import_job_id=import_job.id,
                storage=storage,
            )
    finally:
        db_session.commit = original_commit

    assert _list_trades(db_session) == []
    persisted_job = get_import_job_by_id(db_session, import_job.id)
    assert persisted_job is not None
    assert persisted_job.status is ImportJobStatus.PROCESSING
    assert persisted_job.imported_rows == 0
    assert persisted_job.rejected_rows == 0
    assert persisted_job.total_rows is None


def _write_storage_text(root: Path, storage_key: str, content: str) -> None:
    path = root / storage_key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")


def _write_storage_bytes(root: Path, storage_key: str, content: bytes) -> None:
    path = root / storage_key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _list_trades(db_session: Session) -> list[Trade]:
    return list(db_session.scalars(select(Trade).order_by(Trade.id)))
