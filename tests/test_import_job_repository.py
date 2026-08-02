from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.import_job import ImportJob, ImportJobStatus
from app.repositories.import_job import (
    create_import_job,
    get_import_job_by_id,
    get_import_job_by_id_for_user,
    list_import_jobs_by_user,
    save_import_job,
)
from tests.helpers import create_user_in_db


def test_create_import_job_persists_defaults(db_session: Session) -> None:
    user = create_user_in_db(db_session, "import-owner@example.com")

    import_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="trades.csv",
        storage_key="imports/user-1/trades.csv",
    )

    assert isinstance(import_job, ImportJob)
    assert import_job.id is not None
    assert import_job.user_id == user.id
    assert import_job.status is ImportJobStatus.PENDING
    assert import_job.original_filename == "trades.csv"
    assert import_job.storage_key == "imports/user-1/trades.csv"
    assert import_job.total_rows is None
    assert import_job.imported_rows == 0
    assert import_job.rejected_rows == 0
    assert import_job.failure_message is None
    assert import_job.started_at is None
    assert import_job.completed_at is None
    assert import_job.created_at is not None
    assert import_job.updated_at is not None


def test_get_import_job_by_id_returns_existing_job(db_session: Session) -> None:
    user = create_user_in_db(db_session, "lookup@example.com")
    import_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="lookup.csv",
        storage_key="imports/user-2/lookup.csv",
    )

    found_job = get_import_job_by_id(db_session, import_job.id)

    assert found_job is not None
    assert found_job.id == import_job.id


def test_get_import_job_by_id_returns_none_for_missing_job(db_session: Session) -> None:
    assert get_import_job_by_id(db_session, 999999) is None


def test_get_import_job_by_id_for_user_returns_owned_job(db_session: Session) -> None:
    owner = create_user_in_db(db_session, "owner@example.com")
    import_job = create_import_job(
        db_session,
        user_id=owner.id,
        original_filename="owned.csv",
        storage_key="imports/user-3/owned.csv",
    )

    found_job = get_import_job_by_id_for_user(db_session, import_job.id, owner.id)

    assert found_job is not None
    assert found_job.id == import_job.id
    assert found_job.user_id == owner.id


def test_get_import_job_by_id_for_user_enforces_ownership(db_session: Session) -> None:
    owner = create_user_in_db(db_session, "owner-isolated@example.com")
    other_user = create_user_in_db(db_session, "other-isolated@example.com")
    import_job = create_import_job(
        db_session,
        user_id=owner.id,
        original_filename="private.csv",
        storage_key="imports/user-4/private.csv",
    )

    found_job = get_import_job_by_id_for_user(db_session, import_job.id, other_user.id)

    assert found_job is None


def test_list_import_jobs_by_user_returns_only_owned_jobs(db_session: Session) -> None:
    owner = create_user_in_db(db_session, "list-owner@example.com")
    other_user = create_user_in_db(db_session, "list-other@example.com")
    first_job = create_import_job(
        db_session,
        user_id=owner.id,
        original_filename="first.csv",
        storage_key="imports/user-5/first.csv",
    )
    second_job = create_import_job(
        db_session,
        user_id=owner.id,
        original_filename="second.csv",
        storage_key="imports/user-5/second.csv",
    )
    create_import_job(
        db_session,
        user_id=other_user.id,
        original_filename="other.csv",
        storage_key="imports/user-6/other.csv",
    )

    jobs = list_import_jobs_by_user(db_session, owner.id)

    assert [job.id for job in jobs] == [second_job.id, first_job.id]
    assert all(job.user_id == owner.id for job in jobs)


def test_list_import_jobs_by_user_orders_newest_first(db_session: Session) -> None:
    user = create_user_in_db(db_session, "ordered@example.com")
    older_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="older.csv",
        storage_key="imports/user-7/older.csv",
    )
    newer_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="newer.csv",
        storage_key="imports/user-7/newer.csv",
    )

    older_job.created_at = datetime(2026, 8, 2, 8, 0, tzinfo=UTC)
    newer_job.created_at = datetime(2026, 8, 2, 9, 0, tzinfo=UTC)
    db_session.commit()

    jobs = list_import_jobs_by_user(db_session, user.id)

    assert [job.id for job in jobs] == [newer_job.id, older_job.id]


def test_list_import_jobs_by_user_uses_id_as_deterministic_tiebreaker(
    db_session: Session,
) -> None:
    user = create_user_in_db(db_session, "tie@example.com")
    first_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="first-tie.csv",
        storage_key="imports/user-8/first-tie.csv",
    )
    second_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="second-tie.csv",
        storage_key="imports/user-8/second-tie.csv",
    )

    same_created_at = datetime(2026, 8, 2, 10, 0, tzinfo=UTC)
    first_job.created_at = same_created_at
    second_job.created_at = same_created_at
    db_session.commit()

    jobs = list_import_jobs_by_user(db_session, user.id)

    assert [job.id for job in jobs] == [second_job.id, first_job.id]


def test_list_import_jobs_by_user_applies_limit_and_offset(db_session: Session) -> None:
    user = create_user_in_db(db_session, "paged@example.com")
    jobs = [
        create_import_job(
            db_session,
            user_id=user.id,
            original_filename=f"job-{index}.csv",
            storage_key=f"imports/user-9/job-{index}.csv",
        )
        for index in range(4)
    ]

    paged_jobs = list_import_jobs_by_user(db_session, user.id, limit=2, offset=1)

    expected_ids = [jobs[2].id, jobs[1].id]
    assert [job.id for job in paged_jobs] == expected_ids


def test_save_import_job_persists_updates(db_session: Session) -> None:
    user = create_user_in_db(db_session, "save@example.com")
    import_job = create_import_job(
        db_session,
        user_id=user.id,
        original_filename="save.csv",
        storage_key="imports/user-10/save.csv",
    )

    import_job.status = ImportJobStatus.PROCESSING
    import_job.started_at = datetime(2026, 8, 2, 11, 30, tzinfo=UTC)

    saved_job = save_import_job(db_session, import_job)

    assert saved_job.status is ImportJobStatus.PROCESSING
    assert saved_job.started_at is not None
    assert saved_job.started_at.replace(tzinfo=UTC) == datetime(
        2026,
        8,
        2,
        11,
        30,
        tzinfo=UTC,
    )
