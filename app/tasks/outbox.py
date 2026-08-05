from celery.utils.log import get_task_logger

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.events.publishers import OUTBOX_PUBLISHERS
from app.services.outbox_dispatcher import dispatch_outbox_events
from app.worker.celery_app import celery_app

logger = get_task_logger(__name__)
settings = get_settings()


@celery_app.task(name="app.tasks.outbox.dispatch_outbox_events")
def dispatch_outbox_events_task() -> None:
    try:
        result = dispatch_outbox_events(
            SessionLocal,
            publishers=OUTBOX_PUBLISHERS,
            batch_size=settings.outbox_dispatch_batch_size,
            max_attempts=settings.outbox_dispatch_max_attempts,
        )
    except Exception:
        logger.exception("Outbox dispatcher task failed.")
        raise

    logger.info(
        "Outbox dispatch completed: claimed_count=%s published_count=%s "
        "requeued_count=%s failed_count=%s",
        result.claimed_count,
        result.published_count,
        result.requeued_count,
        result.failed_count,
    )
