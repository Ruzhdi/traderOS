from celery.utils.log import get_task_logger

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.import_job import ImportJobStatus
from app.services import InvalidImportJobTransitionError, fail_import_job
from app.services.trade_import import (
    process_trade_import as process_trade_import_service,
)
from app.storage.import_files import LocalImportFileStorage
from app.worker.celery_app import celery_app

logger = get_task_logger(__name__)
settings = get_settings()

UNEXPECTED_FAILURE_MESSAGE = "Import processing failed unexpectedly."
_DUPLICATE_DELIVERY_STATUSES = {
    ImportJobStatus.PROCESSING,
    ImportJobStatus.COMPLETED,
    ImportJobStatus.FAILED,
}


@celery_app.task(name="app.tasks.imports.process_trade_import")
def process_trade_import_task(import_job_id: int) -> None:
    db = SessionLocal()

    try:
        storage = LocalImportFileStorage(
            root=settings.upload_dir,
            max_size_bytes=settings.max_upload_size_mb * 1024 * 1024,
        )
        import_job = process_trade_import_service(
            db,
            import_job_id=import_job_id,
            storage=storage,
        )
    except InvalidImportJobTransitionError as exc:
        if _is_duplicate_processing_delivery(exc):
            logger.info(
                "Ignoring duplicate or stale trade import task delivery "
                "for import job %s "
                "with current status %s.",
                import_job_id,
                exc.current_status.value,
            )
            return
        raise
    except Exception:
        logger.exception(
            "Trade import task failed unexpectedly for import job %s.",
            import_job_id,
        )
        db.rollback()
        _persist_unexpected_failure(import_job_id)
        raise
    finally:
        db.close()

    if import_job is None:
        logger.info("Trade import job %s was not found.", import_job_id)


def _is_duplicate_processing_delivery(
    exc: InvalidImportJobTransitionError,
) -> bool:
    return (
        exc.target_status is ImportJobStatus.PROCESSING
        and exc.current_status in _DUPLICATE_DELIVERY_STATUSES
    )


def _persist_unexpected_failure(import_job_id: int) -> None:
    failure_db = SessionLocal()

    try:
        fail_import_job(
            failure_db,
            import_job_id,
            failure_message=UNEXPECTED_FAILURE_MESSAGE,
        )
    except Exception:
        failure_db.rollback()
        logger.exception(
            "Failed to persist unexpected import failure state for import job %s.",
            import_job_id,
        )
    finally:
        failure_db.close()
