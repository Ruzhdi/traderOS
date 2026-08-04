from sqlalchemy.orm import Session

from app.models.import_job import ImportJob
from app.repositories.trade import add_trades_for_user
from app.services.import_job import (
    complete_import_job,
    fail_import_job,
    start_import_job,
)
from app.services.trade_csv import InvalidTradeCsvHeaderError, parse_trade_csv
from app.storage.import_files import (
    InvalidImportStorageKeyError,
    LocalImportFileStorage,
)


def process_trade_import(
    db: Session,
    *,
    import_job_id: int,
    storage: LocalImportFileStorage,
) -> ImportJob | None:
    import_job = start_import_job(db, import_job_id)
    if import_job is None:
        return None

    try:
        with storage.open_text(import_job.storage_key) as stream:
            result = parse_trade_csv(stream)
    except FileNotFoundError:
        return fail_import_job(
            db,
            import_job_id,
            failure_message="Import file was not found.",
        )
    except InvalidImportStorageKeyError:
        return fail_import_job(
            db,
            import_job_id,
            failure_message="Import file reference is invalid.",
        )
    except UnicodeDecodeError:
        return fail_import_job(
            db,
            import_job_id,
            failure_message="Import file must be valid UTF-8 CSV text.",
        )
    except InvalidTradeCsvHeaderError as exc:
        return fail_import_job(
            db,
            import_job_id,
            failure_message=_build_invalid_header_message(exc),
        )

    add_trades_for_user(
        db,
        user_id=import_job.user_id,
        trades=result.valid_trades,
    )
    return complete_import_job(
        db,
        import_job_id,
        total_rows=result.total_rows,
        imported_rows=result.valid_rows,
        rejected_rows=result.rejected_rows,
    )


def _build_invalid_header_message(exc: InvalidTradeCsvHeaderError) -> str:
    message_parts: list[str] = []

    if "Trade CSV header is missing" in str(exc):
        message_parts.append("Trade CSV header is missing")
    if "Trade CSV header contains an empty column name" in str(exc):
        message_parts.append("Trade CSV header contains an empty column name")
    if exc.missing_headers:
        message_parts.append(
            "Missing required headers: " + ", ".join(exc.missing_headers)
        )
    if exc.unexpected_headers:
        message_parts.append("Unexpected headers: " + ", ".join(exc.unexpected_headers))
    if exc.duplicate_headers:
        message_parts.append("Duplicate headers: " + ", ".join(exc.duplicate_headers))

    return "; ".join(message_parts) + "."
