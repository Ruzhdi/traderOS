from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.outbox_event import OutboxEvent, OutboxEventStatus
from app.repositories.outbox_event import (
    MAX_ERROR_MESSAGE_LENGTH,
    InvalidOutboxEventTransitionError,
    add_outbox_event,
    claim_pending_outbox_events,
    mark_outbox_event_failed,
    mark_outbox_event_published,
    requeue_outbox_event,
)


def _add_and_commit(
    db_session: Session,
    event_type: str,
    available_at: datetime,
) -> OutboxEvent:
    event = add_outbox_event(
        db_session,
        event_type=event_type,
        payload={"type": event_type},
        available_at=available_at,
    )
    db_session.commit()
    return event


def test_add_outbox_event_flushes_without_committing_and_can_rollback(
    db_session: Session,
) -> None:
    event = add_outbox_event(
        db_session,
        event_type="  trade.created  ",
        payload={"trade_id": 1},
    )
    event_id = event.id

    assert event_id is not None
    assert event.event_type == "trade.created"
    assert event.status is OutboxEventStatus.PENDING
    db_session.rollback()
    assert db_session.get(OutboxEvent, event_id) is None


@pytest.mark.parametrize("event_type", ["", "   "])
def test_add_outbox_event_rejects_empty_event_type(
    db_session: Session,
    event_type: str,
) -> None:
    with pytest.raises(ValueError, match="event_type must not be empty"):
        add_outbox_event(db_session, event_type=event_type, payload={})


def test_add_outbox_event_rejects_non_dict_payload(db_session: Session) -> None:
    with pytest.raises(TypeError, match="payload must be a dict"):
        add_outbox_event(  # type: ignore[arg-type]
            db_session,
            event_type="trade.created",
            payload=[{"trade_id": 1}],
        )


def test_claim_pending_events_is_due_ordered_limited_and_increments_attempts(
    db_session: Session,
) -> None:
    now = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    first = _add_and_commit(db_session, "first", now - timedelta(minutes=2))
    second = _add_and_commit(db_session, "second", now - timedelta(minutes=1))
    _add_and_commit(db_session, "future", now + timedelta(minutes=1))

    claimed = claim_pending_outbox_events(db_session, limit=2, now=now)

    assert [event.id for event in claimed] == [first.id, second.id]
    assert all(event.status is OutboxEventStatus.PROCESSING for event in claimed)
    assert all(event.claimed_at == now for event in claimed)
    assert [event.attempt_count for event in claimed] == [1, 1]


def test_claim_pending_events_uses_id_as_tiebreaker_and_preserves_attempts(
    db_session: Session,
) -> None:
    now = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    first = _add_and_commit(db_session, "first-tie", now)
    second = _add_and_commit(db_session, "second-tie", now)
    first.attempt_count = 2
    db_session.commit()

    claimed = claim_pending_outbox_events(db_session, limit=10, now=now)

    assert [event.id for event in claimed] == [first.id, second.id]
    assert [event.attempt_count for event in claimed] == [3, 1]


def test_claim_pending_events_rejects_non_positive_limit(
    db_session: Session,
) -> None:
    with pytest.raises(ValueError, match="limit must be positive"):
        claim_pending_outbox_events(db_session, limit=0)


def test_claim_changes_can_be_rolled_back(db_session: Session) -> None:
    now = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    event = _add_and_commit(db_session, "rollback-claim", now)
    event_id = event.id

    claim_pending_outbox_events(db_session, limit=1, now=now)
    db_session.rollback()
    stored = db_session.get(OutboxEvent, event_id)

    assert stored is not None
    assert stored.status is OutboxEventStatus.PENDING
    assert stored.attempt_count == 0
    assert stored.claimed_at is None


def test_processing_event_can_be_marked_published(db_session: Session) -> None:
    now = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    event = _add_and_commit(db_session, "publish", now)
    claim_pending_outbox_events(db_session, limit=1, now=now)
    event.last_error = "old error"
    published_at = now + timedelta(seconds=5)

    result = mark_outbox_event_published(
        db_session,
        event_id=event.id,
        published_at=published_at,
    )

    assert result is event
    assert event.status is OutboxEventStatus.PUBLISHED
    assert event.published_at == published_at
    assert event.last_error is None


def test_processing_event_can_be_requeued_with_safe_error(db_session: Session) -> None:
    now = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    event = _add_and_commit(db_session, "requeue", now)
    claim_pending_outbox_events(db_session, limit=1, now=now)
    retry_at = now + timedelta(minutes=5)

    result = requeue_outbox_event(
        db_session,
        event_id=event.id,
        error_message=f"  {'x' * 600}  ",
        available_at=retry_at,
    )

    assert result is event
    assert event.status is OutboxEventStatus.PENDING
    assert event.available_at == retry_at
    assert event.claimed_at is None
    assert event.last_error == "x" * MAX_ERROR_MESSAGE_LENGTH


def test_processing_event_can_be_marked_failed(db_session: Session) -> None:
    now = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    event = _add_and_commit(db_session, "fail", now)
    claim_pending_outbox_events(db_session, limit=1, now=now)

    result = mark_outbox_event_failed(
        db_session,
        event_id=event.id,
        error_message="  delivery rejected  ",
    )

    assert result is event
    assert event.status is OutboxEventStatus.FAILED
    assert event.last_error == "delivery rejected"


@pytest.mark.parametrize("operation", ["requeue", "fail"])
def test_error_transitions_reject_empty_messages(
    db_session: Session,
    operation: str,
) -> None:
    if operation == "requeue":
        transition = requeue_outbox_event
    else:
        transition = mark_outbox_event_failed

    with pytest.raises(ValueError, match="error_message must not be empty"):
        transition(db_session, event_id=1, error_message="   ")


@pytest.mark.parametrize(
    ("transition", "target_status", "kwargs"),
    [
        (mark_outbox_event_published, OutboxEventStatus.PUBLISHED, {}),
        (
            requeue_outbox_event,
            OutboxEventStatus.PENDING,
            {"error_message": "retry"},
        ),
        (
            mark_outbox_event_failed,
            OutboxEventStatus.FAILED,
            {"error_message": "failed"},
        ),
    ],
)
def test_invalid_transition_rolls_back_and_exposes_details(
    db_session: Session,
    transition: object,
    target_status: OutboxEventStatus,
    kwargs: dict[str, str],
) -> None:
    now = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    event = _add_and_commit(db_session, "invalid", now)
    event_id = event.id

    with pytest.raises(InvalidOutboxEventTransitionError) as exc_info:
        transition(db_session, event_id=event_id, **kwargs)  # type: ignore[operator]

    assert exc_info.value.event_id == event_id
    assert exc_info.value.current_status is OutboxEventStatus.PENDING
    assert exc_info.value.target_status is target_status
    assert not db_session.in_transaction()


@pytest.mark.parametrize(
    ("transition", "kwargs"),
    [
        (mark_outbox_event_published, {}),
        (requeue_outbox_event, {"error_message": "retry"}),
        (mark_outbox_event_failed, {"error_message": "failed"}),
    ],
)
def test_transitions_return_none_for_missing_events(
    db_session: Session,
    transition: object,
    kwargs: dict[str, str],
) -> None:
    assert (
        transition(  # type: ignore[operator]
            db_session,
            event_id=999999,
            **kwargs,
        )
        is None
    )


def test_flush_failure_rolls_back_and_is_reraised(db_session: Session) -> None:
    original_flush = db_session.flush
    original_rollback = db_session.rollback
    rollback_calls = 0

    def failing_flush(*args: object, **kwargs: object) -> None:
        raise SQLAlchemyError("flush failed")

    def tracking_rollback() -> None:
        nonlocal rollback_calls
        rollback_calls += 1
        original_rollback()

    db_session.flush = failing_flush
    db_session.rollback = tracking_rollback
    try:
        with pytest.raises(SQLAlchemyError, match="flush failed"):
            add_outbox_event(db_session, event_type="failure", payload={})
    finally:
        db_session.flush = original_flush
        db_session.rollback = original_rollback

    assert rollback_calls == 1
    assert db_session.scalar(select(OutboxEvent)) is None
