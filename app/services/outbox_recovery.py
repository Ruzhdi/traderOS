import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.outbox_event import OutboxEventStatus
from app.repositories.outbox_event import claim_stale_processing_outbox_events

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]

_RECOVERED_MESSAGE = "Stale outbox processing claim was recovered."
_MAX_ATTEMPTS_MESSAGE = "Stale outbox event exceeded maximum processing attempts."


@dataclass(frozen=True)
class OutboxRecoveryResult:
    recovered_count: int
    requeued_count: int
    failed_count: int
    event_ids: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.recovered_count != self.requeued_count + self.failed_count:
            raise ValueError("recovered_count must equal requeued_count + failed_count")


def recover_stale_outbox_events(
    session_factory: SessionFactory,
    *,
    batch_size: int,
    max_attempts: int,
    processing_timeout_seconds: int,
    now: datetime | None = None,
) -> OutboxRecoveryResult:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if max_attempts <= 0:
        raise ValueError("max_attempts must be positive")
    if processing_timeout_seconds <= 0:
        raise ValueError("processing_timeout_seconds must be positive")

    recovery_time = _utc_datetime(now)
    stale_before = recovery_time - timedelta(seconds=processing_timeout_seconds)
    session = session_factory()
    try:
        events = claim_stale_processing_outbox_events(
            session,
            limit=batch_size,
            stale_before=stale_before,
        )
        requeued_count = 0
        failed_count = 0
        event_ids: list[int] = []

        for event in events:
            event_ids.append(event.id)
            if event.attempt_count < max_attempts:
                event.status = OutboxEventStatus.PENDING
                event.available_at = recovery_time
                event.claimed_at = None
                event.last_error = _RECOVERED_MESSAGE
                requeued_count += 1
            else:
                event.status = OutboxEventStatus.FAILED
                event.last_error = _MAX_ATTEMPTS_MESSAGE
                failed_count += 1

        session.commit()
        return OutboxRecoveryResult(
            recovered_count=len(events),
            requeued_count=requeued_count,
            failed_count=failed_count,
            event_ids=tuple(event_ids),
        )
    except Exception:
        session.rollback()
        logger.exception("Failed to recover stale outbox events.")
        raise
    finally:
        session.close()


def _utc_datetime(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC)
