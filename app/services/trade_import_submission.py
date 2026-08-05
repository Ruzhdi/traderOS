import logging
from pathlib import Path
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.events import TRADE_IMPORT_REQUESTED_EVENT
from app.models.import_job import ImportJob
from app.repositories.import_job import add_import_job
from app.repositories.outbox_event import add_outbox_event
from app.storage import LocalImportFileStorage

logger = logging.getLogger(__name__)

INVALID_FILENAME_MESSAGE = "Import filename is invalid."
_MAX_FILENAME_LENGTH = 255


class InvalidTradeImportFilenameError(ValueError):
    pass


def submit_trade_import(
    db: Session,
    *,
    user_id: int,
    original_filename: str,
    stream: BinaryIO,
    storage: LocalImportFileStorage,
) -> ImportJob:
    normalized_filename = _normalize_trade_import_filename(original_filename)
    stored_file = storage.save(stream, user_id=user_id)

    try:
        import_job = add_import_job(
            db,
            user_id=user_id,
            original_filename=normalized_filename,
            storage_key=stored_file.storage_key,
        )
        add_outbox_event(
            db,
            event_type=TRADE_IMPORT_REQUESTED_EVENT,
            payload={"import_job_id": import_job.id},
        )
        db.commit()
    except Exception:
        db.rollback()
        _delete_stored_file(storage, stored_file.storage_key)
        raise

    db.refresh(import_job)
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
