import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy.orm import Session

from app.repositories.outbox_event import (
    claim_pending_outbox_events,
    mark_outbox_event_failed,
    mark_outbox_event_published,
    requeue_outbox_event,
)

logger = logging.getLogger(__name__)

OutboxPublisher = Callable[[dict[str, object]], object]
SessionFactory = Callable[[], Session]

_UNKNOWN_EVENT_TYPE_MESSAGE = "No publisher is registered for this outbox event type."
_RETRY_MESSAGE = "Outbox publication failed and will be retried."
_MAX_ATTEMPTS_MESSAGE = "Outbox publication failed after maximum attempts."


class RetryableOutboxPublishError(Exception):
    """Explicitly marks a publication failure as retryable."""


class UnknownOutboxEventTypeError(LookupError):
    def __init__(self, *, event_id: int, event_type: str) -> None:
        self.event_id = event_id
        self.event_type = event_type
        super().__init__(
            f"No publisher is registered for outbox event {event_id} "
            f"of type {event_type!r}."
        )


class OutboxEventNotFoundDuringDispatchError(LookupError):
    def __init__(self, *, event_id: int, event_type: str) -> None:
        self.event_id = event_id
        self.event_type = event_type
        super().__init__(
            f"Outbox event {event_id} of type {event_type!r} was not found "
            "during finalization."
        )


@dataclass(frozen=True)
class OutboxDispatchFailure:
    event_id: int
    event_type: str
    outcome: Literal["requeued", "failed"]


@dataclass(frozen=True)
class OutboxDispatchResult:
    claimed_count: int
    published_count: int
    requeued_count: int
    failed_count: int
    failures: tuple[OutboxDispatchFailure, ...]

    def __post_init__(self) -> None:
        completed_count = self.published_count + self.requeued_count + self.failed_count
        if self.claimed_count != completed_count:
            raise ValueError(
                "claimed_count must equal published_count + requeued_count + "
                "failed_count"
            )


@dataclass(frozen=True)
class _ClaimedOutboxEvent:
    event_id: int
    event_type: str
    payload: dict[str, object]
    attempt_count: int


def dispatch_outbox_events(
    session_factory: SessionFactory,
    *,
    publishers: Mapping[str, OutboxPublisher],
    batch_size: int,
    max_attempts: int,
    now: datetime | None = None,
) -> OutboxDispatchResult:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if max_attempts <= 0:
        raise ValueError("max_attempts must be positive")
    dispatch_time = _utc_datetime(now)

    claimed_events = _claim_batch(
        session_factory,
        batch_size=batch_size,
        now=dispatch_time,
    )
    published_count = 0
    requeued_count = 0
    failed_count = 0
    failures: list[OutboxDispatchFailure] = []

    for event in claimed_events:
        try:
            publisher = publishers[event.event_type]
        except KeyError:
            error = UnknownOutboxEventTypeError(
                event_id=event.event_id,
                event_type=event.event_type,
            )
            logger.warning(
                "Unknown outbox event type during dispatch: event_id=%s event_type=%s",
                error.event_id,
                error.event_type,
            )
            _mark_failed(
                session_factory,
                event,
                error_message=_UNKNOWN_EVENT_TYPE_MESSAGE,
            )
            failed_count += 1
            failures.append(_failure(event, "failed"))
            continue

        try:
            publisher(event.payload)
        except Exception:
            logger.warning(
                "Outbox publisher failed: event_id=%s event_type=%s",
                event.event_id,
                event.event_type,
            )
            if event.attempt_count < max_attempts:
                delay_seconds = min(2 ** (event.attempt_count - 1) * 30, 3600)
                _requeue(
                    session_factory,
                    event,
                    error_message=_RETRY_MESSAGE,
                    available_at=dispatch_time + timedelta(seconds=delay_seconds),
                )
                requeued_count += 1
                failures.append(_failure(event, "requeued"))
            else:
                _mark_failed(
                    session_factory,
                    event,
                    error_message=_MAX_ATTEMPTS_MESSAGE,
                )
                failed_count += 1
                failures.append(_failure(event, "failed"))
            continue

        _mark_published(session_factory, event, published_at=dispatch_time)
        published_count += 1

    return OutboxDispatchResult(
        claimed_count=len(claimed_events),
        published_count=published_count,
        requeued_count=requeued_count,
        failed_count=failed_count,
        failures=tuple(failures),
    )


def _utc_datetime(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC)


def _claim_batch(
    session_factory: SessionFactory,
    *,
    batch_size: int,
    now: datetime,
) -> list[_ClaimedOutboxEvent]:
    session = session_factory()
    try:
        events = claim_pending_outbox_events(session, limit=batch_size, now=now)
        snapshots = [
            _ClaimedOutboxEvent(
                event_id=event.id,
                event_type=event.event_type,
                payload=event.payload,
                attempt_count=event.attempt_count,
            )
            for event in events
        ]
        session.commit()
        return snapshots
    except Exception:
        session.rollback()
        logger.exception("Failed to claim and commit an outbox event batch.")
        raise
    finally:
        session.close()


def _mark_published(
    session_factory: SessionFactory,
    event: _ClaimedOutboxEvent,
    *,
    published_at: datetime,
) -> None:
    _finalize(
        session_factory,
        event,
        lambda session: mark_outbox_event_published(
            session,
            event_id=event.event_id,
            published_at=published_at,
        ),
    )


def _requeue(
    session_factory: SessionFactory,
    event: _ClaimedOutboxEvent,
    *,
    error_message: str,
    available_at: datetime,
) -> None:
    _finalize(
        session_factory,
        event,
        lambda session: requeue_outbox_event(
            session,
            event_id=event.event_id,
            error_message=error_message,
            available_at=available_at,
        ),
    )


def _mark_failed(
    session_factory: SessionFactory,
    event: _ClaimedOutboxEvent,
    *,
    error_message: str,
) -> None:
    _finalize(
        session_factory,
        event,
        lambda session: mark_outbox_event_failed(
            session,
            event_id=event.event_id,
            error_message=error_message,
        ),
    )


def _finalize(
    session_factory: SessionFactory,
    event: _ClaimedOutboxEvent,
    transition: Callable[[Session], object | None],
) -> None:
    session = session_factory()
    try:
        result = transition(session)
        if result is None:
            raise OutboxEventNotFoundDuringDispatchError(
                event_id=event.event_id,
                event_type=event.event_type,
            )
        session.commit()
    except Exception:
        session.rollback()
        logger.exception(
            "Failed to persist outbox dispatch result: event_id=%s event_type=%s",
            event.event_id,
            event.event_type,
        )
        raise
    finally:
        session.close()


def _failure(
    event: _ClaimedOutboxEvent,
    outcome: Literal["requeued", "failed"],
) -> OutboxDispatchFailure:
    return OutboxDispatchFailure(
        event_id=event.event_id,
        event_type=event.event_type,
        outcome=outcome,
    )
