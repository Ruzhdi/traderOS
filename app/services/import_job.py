from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.import_job import ImportJob, ImportJobStatus
from app.repositories.import_job import get_import_job_by_id_for_update, save_import_job


class InvalidImportJobTransitionError(ValueError):
    def __init__(
        self,
        current_status: ImportJobStatus,
        target_status: ImportJobStatus,
    ) -> None:
        self.current_status = current_status
        self.target_status = target_status
        super().__init__(
            f"Invalid import job transition from {current_status.value} "
            f"to {target_status.value}"
        )


def start_import_job(
    db: Session,
    import_job_id: int,
) -> ImportJob | None:
    import_job = get_import_job_by_id_for_update(db, import_job_id)
    if import_job is None:
        db.rollback()
        return None

    if import_job.status is not ImportJobStatus.PENDING:
        current_status = import_job.status
        db.rollback()
        raise InvalidImportJobTransitionError(
            current_status=current_status,
            target_status=ImportJobStatus.PROCESSING,
        )

    import_job.status = ImportJobStatus.PROCESSING
    import_job.started_at = datetime.now(UTC)
    import_job.completed_at = None
    import_job.failure_message = None

    return save_import_job(db, import_job)


def complete_import_job(
    db: Session,
    import_job_id: int,
    *,
    total_rows: int,
    imported_rows: int,
    rejected_rows: int,
) -> ImportJob | None:
    counters = {
        "total_rows": total_rows,
        "imported_rows": imported_rows,
        "rejected_rows": rejected_rows,
    }
    for field_name, value in counters.items():
        if value < 0:
            raise ValueError(f"{field_name} must be non-negative")

    import_job = get_import_job_by_id_for_update(db, import_job_id)
    if import_job is None:
        db.rollback()
        return None

    if import_job.status is not ImportJobStatus.PROCESSING:
        current_status = import_job.status
        db.rollback()
        raise InvalidImportJobTransitionError(
            current_status=current_status,
            target_status=ImportJobStatus.COMPLETED,
        )

    import_job.status = ImportJobStatus.COMPLETED
    import_job.total_rows = total_rows
    import_job.imported_rows = imported_rows
    import_job.rejected_rows = rejected_rows
    import_job.completed_at = datetime.now(UTC)
    import_job.failure_message = None

    return save_import_job(db, import_job)


def fail_import_job(
    db: Session,
    import_job_id: int,
    *,
    failure_message: str,
) -> ImportJob | None:
    normalized_failure_message = failure_message.strip()
    if not normalized_failure_message:
        raise ValueError("failure_message must not be empty")

    import_job = get_import_job_by_id_for_update(db, import_job_id)
    if import_job is None:
        db.rollback()
        return None

    if import_job.status not in {
        ImportJobStatus.PENDING,
        ImportJobStatus.PROCESSING,
    }:
        current_status = import_job.status
        db.rollback()
        raise InvalidImportJobTransitionError(
            current_status=current_status,
            target_status=ImportJobStatus.FAILED,
        )

    import_job.status = ImportJobStatus.FAILED
    import_job.completed_at = datetime.now(UTC)
    import_job.failure_message = normalized_failure_message

    return save_import_job(db, import_job)
