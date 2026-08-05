from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.outbox_event import OutboxEvent, OutboxEventStatus

MAX_ERROR_MESSAGE_LENGTH = 500


class InvalidOutboxEventTransitionError(Exception):
    def __init__(
        self,
        *,
        event_id: int,
        current_status: OutboxEventStatus,
        target_status: OutboxEventStatus,
    ) -> None:
        self.event_id = event_id
        self.current_status = current_status
        self.target_status = target_status
        super().__init__(
            f"Cannot transition outbox event {event_id} from "
            f"{current_status.value} to {target_status.value}."
        )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _safe_error_message(error_message: str) -> str:
    if not isinstance(error_message, str):
        raise TypeError("error_message must be a string")

    safe_message = error_message.strip()
    if not safe_message:
        raise ValueError("error_message must not be empty")
    return safe_message[:MAX_ERROR_MESSAGE_LENGTH]


def _flush_or_rollback(db: Session) -> None:
    try:
        db.flush()
    except SQLAlchemyError:
        db.rollback()
        raise


def add_outbox_event(
    db: Session,
    *,
    event_type: str,
    payload: dict[str, Any],
    available_at: datetime | None = None,
) -> OutboxEvent:
    if not isinstance(event_type, str):
        raise TypeError("event_type must be a string")

    normalized_event_type = event_type.strip()
    if not normalized_event_type:
        raise ValueError("event_type must not be empty")
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")

    event = OutboxEvent(event_type=normalized_event_type, payload=payload)
    if available_at is not None:
        event.available_at = available_at
    db.add(event)
    _flush_or_rollback(db)
    return event


def claim_pending_outbox_events(
    db: Session,
    *,
    limit: int,
    now: datetime | None = None,
) -> list[OutboxEvent]:
    if limit <= 0:
        raise ValueError("limit must be positive")

    claimed_at = now or _utc_now()
    statement = (
        select(OutboxEvent)
        .where(
            OutboxEvent.status == OutboxEventStatus.PENDING,
            OutboxEvent.available_at <= claimed_at,
        )
        .order_by(OutboxEvent.available_at.asc(), OutboxEvent.id.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    events = list(db.scalars(statement))

    for event in events:
        event.status = OutboxEventStatus.PROCESSING
        event.claimed_at = claimed_at
        event.attempt_count += 1

    _flush_or_rollback(db)
    return events


def claim_stale_processing_outbox_events(
    db: Session,
    *,
    limit: int,
    stale_before: datetime,
) -> list[OutboxEvent]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    if stale_before.tzinfo is None or stale_before.utcoffset() is None:
        raise ValueError("stale_before must be timezone-aware")

    statement = (
        select(OutboxEvent)
        .where(
            OutboxEvent.status == OutboxEventStatus.PROCESSING,
            or_(
                OutboxEvent.claimed_at <= stale_before,
                OutboxEvent.claimed_at.is_(None),
            ),
        )
        .order_by(OutboxEvent.claimed_at.asc().nulls_first(), OutboxEvent.id.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list(db.scalars(statement))


def _get_for_transition(db: Session, event_id: int) -> OutboxEvent | None:
    statement = select(OutboxEvent).where(OutboxEvent.id == event_id).with_for_update()
    return db.scalar(statement)


def _require_processing(
    db: Session,
    event: OutboxEvent,
    target_status: OutboxEventStatus,
) -> None:
    if event.status is OutboxEventStatus.PROCESSING:
        return

    event_id = event.id
    current_status = event.status
    db.rollback()
    raise InvalidOutboxEventTransitionError(
        event_id=event_id,
        current_status=current_status,
        target_status=target_status,
    )


def mark_outbox_event_published(
    db: Session,
    *,
    event_id: int,
    published_at: datetime | None = None,
) -> OutboxEvent | None:
    event = _get_for_transition(db, event_id)
    if event is None:
        return None
    _require_processing(db, event, OutboxEventStatus.PUBLISHED)

    event.status = OutboxEventStatus.PUBLISHED
    event.published_at = published_at or _utc_now()
    event.last_error = None
    _flush_or_rollback(db)
    return event


def requeue_outbox_event(
    db: Session,
    *,
    event_id: int,
    error_message: str,
    available_at: datetime | None = None,
) -> OutboxEvent | None:
    safe_message = _safe_error_message(error_message)
    event = _get_for_transition(db, event_id)
    if event is None:
        return None
    _require_processing(db, event, OutboxEventStatus.PENDING)

    event.status = OutboxEventStatus.PENDING
    event.available_at = available_at or _utc_now()
    event.last_error = safe_message
    event.claimed_at = None
    _flush_or_rollback(db)
    return event


def mark_outbox_event_failed(
    db: Session,
    *,
    event_id: int,
    error_message: str,
) -> OutboxEvent | None:
    safe_message = _safe_error_message(error_message)
    event = _get_for_transition(db, event_id)
    if event is None:
        return None
    _require_processing(db, event, OutboxEventStatus.FAILED)

    event.status = OutboxEventStatus.FAILED
    event.last_error = safe_message
    _flush_or_rollback(db)
    return event
