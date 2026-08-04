import logging
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.models.import_job import ImportJob
from app.repositories.import_job import create_import_job
from app.services.import_job import fail_import_job
from app.storage import LocalImportFileStorage

logger = logging.getLogger(__name__)

INVALID_FILENAME_MESSAGE = "Import filename is invalid."
QUEUE_FAILURE_MESSAGE = "Import could not be queued for processing."
_MAX_FILENAME_LENGTH = 255


class InvalidTradeImportFilenameError(ValueError):
    pass


class TradeImportEnqueueError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(QUEUE_FAILURE_MESSAGE)


def submit_trade_import(
    db: Session,
    *,
    user_id: int,
    original_filename: str,
    stream: BinaryIO,
    storage: LocalImportFileStorage,
    enqueue: Callable[[int], object],
) -> ImportJob:
    normalized_filename = _normalize_trade_import_filename(original_filename)
    stored_file = storage.save(stream, user_id=user_id)

    try:
        import_job = create_import_job(
            db,
            user_id=user_id,
            original_filename=normalized_filename,
            storage_key=stored_file.storage_key,
        )
    except Exception:
        _delete_stored_file(storage, stored_file.storage_key)
        raise

    try:
        enqueue(import_job.id)
    except Exception as exc:
        _mark_import_job_failed(db, import_job.id)
        _delete_stored_file(storage, stored_file.storage_key)
        raise TradeImportEnqueueError() from exc

    return import_job


def _normalize_trade_import_filename(original_filename: str) -> str:
    if "\x00" in original_filename:
        raise InvalidTradeImportFilenameError(INVALID_FILENAME_MESSAGE)

    normalized_path = original_filename.replace("\\", "/")
    basename = normalized_path.rsplit("/", maxsplit=1)[-1].strip()

    if not basename:
        raise InvalidTradeImportFilenameError(INVALID_FILENAME_MESSAGE)
    if len(basename) > _MAX_FILENAME_LENGTH:
        raise InvalidTradeImportFilenameError(INVALID_FILENAME_MESSAGE)
    if Path(basename).suffix.lower() != ".csv":
        raise InvalidTradeImportFilenameError(INVALID_FILENAME_MESSAGE)

    return basename


def _mark_import_job_failed(db: Session, import_job_id: int) -> None:
    try:
        fail_import_job(
            db,
            import_job_id,
            failure_message=QUEUE_FAILURE_MESSAGE,
        )
    except Exception:
        logger.exception(
            "Failed to mark trade import job %s as failed after enqueue error.",
            import_job_id,
        )


def _delete_stored_file(
    storage: LocalImportFileStorage,
    storage_key: str,
) -> None:
    try:
        storage.delete(storage_key)
    except Exception:
        logger.exception(
            "Failed to delete stored trade import file %s during cleanup.",
            storage_key,
        )
