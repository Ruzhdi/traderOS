import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.outbox_event import OutboxEventStatus
from app.repositories.outbox_event import claim_expired_terminal_outbox_events

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]


@dataclass(frozen=True)
class OutboxCleanupResult:
    deleted_count: int
    published_deleted_count: int
    failed_deleted_count: int
    event_ids: tuple[int, ...]

    def __post_init__(self) -> None:
        terminal_count = self.published_deleted_count + self.failed_deleted_count
        if self.deleted_count != terminal_count:
            raise ValueError(
                "deleted_count must equal published_deleted_count + "
                "failed_deleted_count"
            )
        if self.deleted_count != len(self.event_ids):
            raise ValueError("deleted_count must equal the number of event_ids")


def cleanup_terminal_outbox_events(
    session_factory: SessionFactory,
    *,
    batch_size: int,
    published_retention_days: int,
    failed_retention_days: int,
    now: datetime | None = None,
) -> OutboxCleanupResult:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if published_retention_days <= 0:
        raise ValueError("published_retention_days must be positive")
    if failed_retention_days <= 0:
        raise ValueError("failed_retention_days must be positive")

    cleanup_time = _utc_datetime(now)
    published_before = cleanup_time - timedelta(days=published_retention_days)
    failed_before = cleanup_time - timedelta(days=failed_retention_days)
    session = session_factory()
    try:
        events = claim_expired_terminal_outbox_events(
            session,
            limit=batch_size,
            published_before=published_before,
            failed_before=failed_before,
        )
        snapshots = tuple((event.id, event.status) for event in events)
        for event in events:
            session.delete(event)
        session.commit()

        return OutboxCleanupResult(
            deleted_count=len(snapshots),
            published_deleted_count=sum(
                status is OutboxEventStatus.PUBLISHED for _, status in snapshots
            ),
            failed_deleted_count=sum(
                status is OutboxEventStatus.FAILED for _, status in snapshots
            ),
            event_ids=tuple(event_id for event_id, _ in snapshots),
        )
    except Exception:
        session.rollback()
        logger.exception("Failed to clean up terminal outbox events.")
        raise
    finally:
        session.close()


def _utc_datetime(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC)
