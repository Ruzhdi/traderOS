import pytest
from sqlalchemy.orm import Session

from app.models.import_job import ImportJobStatus
from app.repositories.import_job import create_import_job, get_import_job_by_id
from app.services.import_job import (
    InvalidImportJobTransitionError,
    complete_import_job,
    fail_import_job,
    start_import_job,
)
from tests.helpers import create_user_in_db


def test_start_import_job_transitions_pending_to_processing(
    db_session: Session,
) -> None:
    user = create_user_in_db(db_session, "start@example.com")
    import_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="start.csv",
        storage_key="imports/service/start.csv",
    )

    started_job = start_import_job(db_session, import_job.id)

    assert started_job is not None
    assert started_job.status is ImportJobStatus.PROCESSING
    assert started_job.started_at is not None
    assert started_job.completed_at is None
    assert started_job.failure_message is None


def test_complete_import_job_transitions_processing_to_completed(
    db_session: Session,
) -> None:
    user = create_user_in_db(db_session, "complete@example.com")
    import_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="complete.csv",
        storage_key="imports/service/complete.csv",
    )
    started_job = start_import_job(db_session, import_job.id)
    assert started_job is not None
    original_started_at = started_job.started_at

    completed_job = complete_import_job(
        db_session,
        import_job.id,
        total_rows=12,
        imported_rows=10,
        rejected_rows=2,
    )

    assert completed_job is not None
    assert completed_job.status is ImportJobStatus.COMPLETED
    assert completed_job.total_rows == 12
    assert completed_job.imported_rows == 10
    assert completed_job.rejected_rows == 2
    assert completed_job.completed_at is not None
    assert completed_job.started_at == original_started_at
    assert completed_job.failure_message is None


def test_fail_import_job_transitions_pending_to_failed(db_session: Session) -> None:
    user = create_user_in_db(db_session, "fail-pending@example.com")
    import_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="pending-fail.csv",
        storage_key="imports/service/pending-fail.csv",
    )

    failed_job = fail_import_job(
        db_session,
        import_job.id,
        failure_message="  Missing required columns.  ",
    )

    assert failed_job is not None
    assert failed_job.status is ImportJobStatus.FAILED
    assert failed_job.completed_at is not None
    assert failed_job.started_at is None
    assert failed_job.failure_message == "Missing required columns."


def test_fail_import_job_transitions_processing_to_failed(db_session: Session) -> None:
    user = create_user_in_db(db_session, "fail-processing@example.com")
    import_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="processing-fail.csv",
        storage_key="imports/service/processing-fail.csv",
    )
    started_job = start_import_job(db_session, import_job.id)
    assert started_job is not None
    original_started_at = started_job.started_at

    failed_job = fail_import_job(
        db_session,
        import_job.id,
        failure_message="Row parsing failed.",
    )

    assert failed_job is not None
    assert failed_job.status is ImportJobStatus.FAILED
    assert failed_job.completed_at is not None
    assert failed_job.started_at == original_started_at
    assert failed_job.failure_message == "Row parsing failed."


def test_fail_import_job_rejects_empty_failure_message(db_session: Session) -> None:
    user = create_user_in_db(db_session, "empty-message@example.com")
    import_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="empty-message.csv",
        storage_key="imports/service/empty-message.csv",
    )

    with pytest.raises(ValueError, match="failure_message must not be empty"):
        fail_import_job(
            db_session,
            import_job.id,
            failure_message="   ",
        )


@pytest.mark.parametrize(
    ("total_rows", "imported_rows", "rejected_rows", "field_name"),
    [
        (-1, 0, 0, "total_rows"),
        (1, -1, 0, "imported_rows"),
        (1, 0, -1, "rejected_rows"),
    ],
)
def test_complete_import_job_rejects_negative_counters(
    db_session: Session,
    total_rows: int,
    imported_rows: int,
    rejected_rows: int,
    field_name: str,
) -> None:
    user = create_user_in_db(db_session, f"{field_name}@example.com")
    import_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename=f"{field_name}.csv",
        storage_key=f"imports/service/{field_name}.csv",
    )
    started_job = start_import_job(db_session, import_job.id)
    assert started_job is not None

    with pytest.raises(ValueError, match=field_name):
        complete_import_job(
            db_session,
            import_job.id,
            total_rows=total_rows,
            imported_rows=imported_rows,
            rejected_rows=rejected_rows,
        )


def test_complete_import_job_rejects_pending_to_completed_transition(
    db_session: Session,
) -> None:
    user = create_user_in_db(db_session, "pending-complete@example.com")
    import_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="pending-complete.csv",
        storage_key="imports/service/pending-complete.csv",
    )

    with pytest.raises(InvalidImportJobTransitionError) as exc_info:
        complete_import_job(
            db_session,
            import_job.id,
            total_rows=3,
            imported_rows=3,
            rejected_rows=0,
        )

    assert exc_info.value.current_status is ImportJobStatus.PENDING
    assert exc_info.value.target_status is ImportJobStatus.COMPLETED


def test_completed_import_job_is_terminal(db_session: Session) -> None:
    user = create_user_in_db(db_session, "terminal-completed@example.com")
    import_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="terminal-completed.csv",
        storage_key="imports/service/terminal-completed.csv",
    )
    started_job = start_import_job(db_session, import_job.id)
    assert started_job is not None
    completed_job = complete_import_job(
        db_session,
        import_job.id,
        total_rows=5,
        imported_rows=5,
        rejected_rows=0,
    )
    assert completed_job is not None

    with pytest.raises(InvalidImportJobTransitionError) as exc_info:
        fail_import_job(
            db_session,
            import_job.id,
            failure_message="Should not be allowed.",
        )

    assert exc_info.value.current_status is ImportJobStatus.COMPLETED
    assert exc_info.value.target_status is ImportJobStatus.FAILED


def test_failed_import_job_is_terminal(db_session: Session) -> None:
    user = create_user_in_db(db_session, "terminal-failed@example.com")
    import_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="terminal-failed.csv",
        storage_key="imports/service/terminal-failed.csv",
    )
    failed_job = fail_import_job(
        db_session,
        import_job.id,
        failure_message="Initial failure.",
    )
    assert failed_job is not None

    with pytest.raises(InvalidImportJobTransitionError) as exc_info:
        start_import_job(db_session, import_job.id)

    assert exc_info.value.current_status is ImportJobStatus.FAILED
    assert exc_info.value.target_status is ImportJobStatus.PROCESSING


@pytest.mark.parametrize("operation", ["start", "complete", "fail"])
def test_import_job_service_returns_none_for_missing_job(
    db_session: Session,
    operation: str,
) -> None:
    if operation == "start":
        result = start_import_job(db_session, 999999)
    elif operation == "complete":
        result = complete_import_job(
            db_session,
            999999,
            total_rows=1,
            imported_rows=1,
            rejected_rows=0,
        )
    else:
        result = fail_import_job(
            db_session,
            999999,
            failure_message="Missing job.",
        )

    assert result is None


def test_invalid_transition_leaves_persisted_state_unchanged(
    db_session: Session,
) -> None:
    user = create_user_in_db(db_session, "unchanged@example.com")
    import_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="unchanged.csv",
        storage_key="imports/service/unchanged.csv",
    )

    with pytest.raises(InvalidImportJobTransitionError):
        complete_import_job(
            db_session,
            import_job.id,
            total_rows=4,
            imported_rows=4,
            rejected_rows=0,
        )

    persisted_job = get_import_job_by_id(db_session, import_job.id)

    assert persisted_job is not None
    assert persisted_job.status is ImportJobStatus.PENDING
    assert persisted_job.total_rows is None
    assert persisted_job.imported_rows == 0
    assert persisted_job.rejected_rows == 0
    assert persisted_job.started_at is None
    assert persisted_job.completed_at is None
    assert persisted_job.failure_message is None


def test_session_remains_usable_after_domain_validation_error(
    db_session: Session,
) -> None:
    user = create_user_in_db(db_session, "session-usable@example.com")
    import_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="session-usable.csv",
        storage_key="imports/service/session-usable.csv",
    )

    with pytest.raises(ValueError, match="failure_message must not be empty"):
        fail_import_job(
            db_session,
            import_job.id,
            failure_message="   ",
        )

    started_job = start_import_job(db_session, import_job.id)

    assert started_job is not None
    assert started_job.status is ImportJobStatus.PROCESSING
