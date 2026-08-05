from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_import_file_storage
from app.db.session import get_db
from app.models.user import User
from app.repositories import get_import_job_by_id_for_user, list_import_jobs_by_user
from app.schemas import ImportJobRead
from app.services import (
    InvalidTradeImportFilenameError,
    submit_trade_import,
)
from app.storage import ImportFileTooLargeError, LocalImportFileStorage

router = APIRouter(prefix="/trade-imports", tags=["Trade Imports"])


@router.get("", response_model=list[ImportJobRead], status_code=status.HTTP_200_OK)
def list_trade_imports_for_current_user(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ImportJobRead]:
    import_jobs = list_import_jobs_by_user(
        db,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return [ImportJobRead.model_validate(import_job) for import_job in import_jobs]


@router.get(
    "/{import_job_id}",
    response_model=ImportJobRead,
    status_code=status.HTTP_200_OK,
)
def get_trade_import_for_current_user(
    import_job_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ImportJobRead:
    import_job = get_import_job_by_id_for_user(
        db,
        import_job_id=import_job_id,
        user_id=current_user.id,
    )
    if import_job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trade import job not found.",
        )

    return ImportJobRead.model_validate(import_job)


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
    return ImportJobRead.model_validate(import_job)
