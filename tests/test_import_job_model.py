from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.import_job import ImportJob, ImportJobStatus
from tests.helpers import create_user_in_db


def test_import_job_can_be_created_and_selected_for_a_user(
    db_session: Session,
) -> None:
    user = create_user_in_db(db_session, "importer@example.com")
    started_at = datetime(2026, 8, 2, 9, 30, tzinfo=UTC)
    completed_at = datetime(2026, 8, 2, 9, 45, tzinfo=UTC)

    job = ImportJob(
        user_id=user.id,
        original_filename="trades-july.csv",
        storage_key="imports/user-1/trades-july.csv",
        status=ImportJobStatus.COMPLETED,
        total_rows=25,
        imported_rows=23,
        rejected_rows=2,
        failure_message="2 rows were skipped due to missing symbols.",
        started_at=started_at,
        completed_at=completed_at,
    )
    db_session.add(job)
    db_session.commit()

    stored_job = db_session.scalar(select(ImportJob).where(ImportJob.id == job.id))

    assert stored_job is not None
    assert stored_job.user_id == user.id
    assert stored_job.status is ImportJobStatus.COMPLETED
    assert stored_job.original_filename == "trades-july.csv"
    assert stored_job.storage_key == "imports/user-1/trades-july.csv"
    assert stored_job.total_rows == 25
    assert stored_job.imported_rows == 23
    assert stored_job.rejected_rows == 2
    assert stored_job.failure_message == "2 rows were skipped due to missing symbols."
    assert stored_job.started_at is not None
    assert stored_job.started_at.replace(tzinfo=UTC) == started_at
    assert stored_job.completed_at is not None
    assert stored_job.completed_at.replace(tzinfo=UTC) == completed_at
    assert stored_job.created_at is not None
    assert stored_job.updated_at is not None


def test_import_job_defaults_are_applied(db_session: Session) -> None:
    user = create_user_in_db(db_session, "defaults@example.com")

    job = ImportJob(
        user_id=user.id,
        original_filename="default-import.csv",
        storage_key="imports/user-2/default-import.csv",
    )
    db_session.add(job)
    db_session.commit()

    stored_job = db_session.scalar(select(ImportJob).where(ImportJob.id == job.id))

    assert stored_job is not None
    assert stored_job.status is ImportJobStatus.PENDING
    assert stored_job.imported_rows == 0
    assert stored_job.rejected_rows == 0
    assert stored_job.total_rows is None
    assert isinstance(stored_job.status, ImportJobStatus)


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("total_rows", -1),
        ("imported_rows", -1),
        ("rejected_rows", -1),
    ],
)
def test_import_job_rejects_negative_counters(
    db_session: Session,
    field_name: str,
    field_value: int,
) -> None:
    user = create_user_in_db(db_session, f"{field_name}@example.com")

    job_kwargs = {
        "user_id": user.id,
        "original_filename": f"{field_name}.csv",
        "storage_key": f"imports/{field_name}.csv",
        field_name: field_value,
    }

    db_session.add(ImportJob(**job_kwargs))

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()


def test_import_job_rejects_duplicate_storage_key(db_session: Session) -> None:
    first_user = create_user_in_db(db_session, "duplicate-a@example.com")
    second_user = create_user_in_db(db_session, "duplicate-b@example.com")

    storage_key = "imports/shared/key.csv"

    db_session.add(
        ImportJob(
            user_id=first_user.id,
            original_filename="first.csv",
            storage_key=storage_key,
        )
    )
    db_session.commit()

    db_session.add(
        ImportJob(
            user_id=second_user.id,
            original_filename="second.csv",
            storage_key=storage_key,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()
