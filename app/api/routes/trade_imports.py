from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_import_file_storage
from app.db.session import get_db
from app.models.user import User
from app.schemas import ImportJobRead
from app.services import (
    InvalidTradeImportFilenameError,
    TradeImportEnqueueError,
    submit_trade_import,
)
from app.storage import ImportFileTooLargeError, LocalImportFileStorage
from app.tasks import process_trade_import_task

router = APIRouter(prefix="/trade-imports", tags=["Trade Imports"])


def _enqueue_trade_import(import_job_id: int) -> object:
    return process_trade_import_task.delay(import_job_id)


@router.post("", response_model=ImportJobRead, status_code=status.HTTP_202_ACCEPTED)
def create_trade_import_for_current_user(
    file: Annotated[UploadFile, File(...)],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    storage: Annotated[LocalImportFileStorage, Depends(get_import_file_storage)],
) -> ImportJobRead:
    try:
        import_job = submit_trade_import(
            db,
            user_id=current_user.id,
            original_filename=file.filename or "",
            stream=file.file,
            storage=storage,
            enqueue=_enqueue_trade_import,
        )
    except InvalidTradeImportFilenameError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ImportFileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except TradeImportEnqueueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return ImportJobRead.model_validate(import_job)
