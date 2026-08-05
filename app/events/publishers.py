from app.events.types import TRADE_IMPORT_REQUESTED_EVENT
from app.services.outbox_dispatcher import (
    OutboxPublisher,
    PermanentOutboxPublishError,
)


def publish_trade_import_requested(payload: dict[str, object]) -> object:
    if set(payload) != {"import_job_id"}:
        raise PermanentOutboxPublishError

    import_job_id = payload["import_job_id"]
    if (
        not isinstance(import_job_id, int)
        or isinstance(import_job_id, bool)
        or import_job_id <= 0
    ):
        raise PermanentOutboxPublishError

    # Import at publication time to keep task package exports free of import cycles.
    from app.tasks.imports import process_trade_import_task

    return process_trade_import_task.delay(import_job_id)


OUTBOX_PUBLISHERS: dict[str, OutboxPublisher] = {
    TRADE_IMPORT_REQUESTED_EVENT: publish_trade_import_requested,
}

__all__ = ["OUTBOX_PUBLISHERS", "publish_trade_import_requested"]
