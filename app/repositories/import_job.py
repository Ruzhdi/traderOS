from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.import_job import ImportJob


def create_import_job(
    db: Session,
    user_id: int,
    original_filename: str,
    storage_key: str,
) -> ImportJob:
    import_job = ImportJob(
        user_id=user_id,
        original_filename=original_filename,
        storage_key=storage_key,
    )
    db.add(import_job)

    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    db.refresh(import_job)
    return import_job


def get_import_job_by_id(
    db: Session,
    import_job_id: int,
) -> ImportJob | None:
    statement = select(ImportJob).where(ImportJob.id == import_job_id)
    return db.scalar(statement)


def get_import_job_by_id_for_user(
    db: Session,
    import_job_id: int,
    user_id: int,
) -> ImportJob | None:
    statement = select(ImportJob).where(
        ImportJob.id == import_job_id,
        ImportJob.user_id == user_id,
    )
    return db.scalar(statement)


def list_import_jobs_by_user(
    db: Session,
    user_id: int,
    limit: int = 20,
    offset: int = 0,
) -> list[ImportJob]:
    statement = (
        select(ImportJob)
        .where(ImportJob.user_id == user_id)
        .order_by(ImportJob.created_at.desc(), ImportJob.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement))


def get_import_job_by_id_for_update(
    db: Session,
    import_job_id: int,
) -> ImportJob | None:
    statement = select(ImportJob).where(ImportJob.id == import_job_id).with_for_update()
    return db.scalar(statement)


def save_import_job(
    db: Session,
    import_job: ImportJob,
) -> ImportJob:
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    db.refresh(import_job)
    return import_job
