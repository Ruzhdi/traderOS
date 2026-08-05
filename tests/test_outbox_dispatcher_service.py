from collections.abc import Callable, Generator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.models.outbox_event import OutboxEvent, OutboxEventStatus
from app.repositories.outbox_event import add_outbox_event
from app.services.outbox_dispatcher import (
    OutboxDispatchFailure,
    OutboxDispatchResult,
    OutboxEventNotFoundDuringDispatchError,
    PermanentOutboxPublishError,
    RetryableOutboxPublishError,
    UnknownOutboxEventTypeError,
    dispatch_outbox_events,
)

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


class TrackingSession(Session):
    created: list[TrackingSession] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.commit_count = 0
        self.rollback_count = 0
        self.was_closed = False
        self.created.append(self)

    def commit(self) -> None:
        self.commit_count += 1
        super().commit()

    def rollback(self) -> None:
        self.rollback_count += 1
        super().rollback()

    def close(self) -> None:
        self.was_closed = True
        super().close()


@pytest.fixture
def session_factory(db_session: Session) -> Generator[Callable[[], Session]]:
    TrackingSession.created = []
    factory = sessionmaker(
        bind=db_session.get_bind(),
        class_=TrackingSession,
        autocommit=False,
        autoflush=False,
    )
    yield factory
    for session in TrackingSession.created:
        session.close()


def _event(
    db_session: Session,
    event_type: str,
    *,
    payload: dict[str, object] | None = None,
    available_at: datetime = NOW,
    attempt_count: int = 0,
) -> int:
    event = add_outbox_event(
        db_session,
        event_type=event_type,
        payload=payload or {"event_type": event_type},
        available_at=available_at,
    )
    event.attempt_count = attempt_count
    db_session.commit()
    return event.id


def _stored(db_session: Session, event_id: int) -> OutboxEvent:
    db_session.expire_all()
    event = db_session.get(OutboxEvent, event_id)
    assert event is not None
    return event


@pytest.mark.parametrize(
    ("batch_size", "max_attempts", "message"),
    [(0, 1, "batch_size"), (-1, 1, "batch_size"), (1, 0, "max_attempts")],
)
def test_rejects_non_positive_configuration(
    session_factory: Callable[[], Session],
    batch_size: int,
    max_attempts: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        dispatch_outbox_events(
            session_factory,
            publishers={},
            batch_size=batch_size,
            max_attempts=max_attempts,
            now=NOW,
        )


def test_rejects_naive_now(session_factory: Callable[[], Session]) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        dispatch_outbox_events(
            session_factory,
            publishers={},
            batch_size=1,
            max_attempts=1,
            now=datetime(2026, 8, 4),
        )


def test_result_enforces_counter_invariant() -> None:
    with pytest.raises(ValueError, match="claimed_count"):
        OutboxDispatchResult(1, 0, 0, 0, ())


def test_empty_batch_returns_zero_result_and_closes_claim_session(
    session_factory: Callable[[], Session],
) -> None:
    result = dispatch_outbox_events(
        session_factory, publishers={}, batch_size=5, max_attempts=3, now=NOW
    )

    assert result == OutboxDispatchResult(0, 0, 0, 0, ())
    assert len(TrackingSession.created) == 1
    assert TrackingSession.created[0].commit_count == 1
    assert TrackingSession.created[0].was_closed


def test_future_events_are_excluded(
    db_session: Session, session_factory: Callable[[], Session]
) -> None:
    event_id = _event(db_session, "future", available_at=NOW + timedelta(seconds=1))

    result = dispatch_outbox_events(
        session_factory,
        publishers={"future": lambda payload: None},
        batch_size=5,
        max_attempts=3,
        now=NOW,
    )

    assert result.claimed_count == 0
    assert _stored(db_session, event_id).status is OutboxEventStatus.PENDING


def test_success_passes_only_payload_and_finalizes_in_a_new_session(
    db_session: Session, session_factory: Callable[[], Session]
) -> None:
    payload = {"trade_id": 42}
    event_id = _event(db_session, "trade.created", payload=payload)
    received: list[dict[str, object]] = []

    result = dispatch_outbox_events(
        session_factory,
        publishers={"trade.created": received.append},
        batch_size=1,
        max_attempts=3,
        now=NOW,
    )

    assert received == [payload]
    assert result == OutboxDispatchResult(1, 1, 0, 0, ())
    stored = _stored(db_session, event_id)
    assert stored.status is OutboxEventStatus.PUBLISHED
    assert stored.published_at is not None
    assert len(TrackingSession.created) == 2
    assert all(session.commit_count == 1 for session in TrackingSession.created)
    assert all(session.was_closed for session in TrackingSession.created)


def test_claim_is_committed_and_session_closed_before_publisher(
    db_session: Session, session_factory: Callable[[], Session]
) -> None:
    event_id = _event(db_session, "ordered")

    def publisher(payload: dict[str, object]) -> None:
        claim_session = TrackingSession.created[0]
        assert claim_session.commit_count == 1
        assert claim_session.was_closed
        assert not claim_session.in_transaction()
        with session_factory() as observer:
            event = observer.get(OutboxEvent, event_id)
            assert event is not None
            assert event.status is OutboxEventStatus.PROCESSING

    dispatch_outbox_events(
        session_factory,
        publishers={"ordered": publisher},
        batch_size=1,
        max_attempts=3,
        now=NOW,
    )


def test_deterministic_order_and_batch_limit(
    db_session: Session, session_factory: Callable[[], Session]
) -> None:
    _event(db_session, "second", available_at=NOW - timedelta(seconds=1))
    _event(db_session, "first", available_at=NOW - timedelta(seconds=2))
    third_id = _event(db_session, "third", available_at=NOW)
    calls: list[str] = []

    result = dispatch_outbox_events(
        session_factory,
        publishers={
            "first": lambda payload: calls.append("first"),
            "second": lambda payload: calls.append("second"),
            "third": lambda payload: calls.append("third"),
        },
        batch_size=2,
        max_attempts=3,
        now=NOW,
    )

    assert calls == ["first", "second"]
    assert result.claimed_count == 2
    assert _stored(db_session, third_id).status is OutboxEventStatus.PENDING


def test_unknown_type_is_safely_failed_and_exception_exposes_identifiers(
    db_session: Session, session_factory: Callable[[], Session]
) -> None:
    event_id = _event(db_session, "unknown")

    result = dispatch_outbox_events(
        session_factory, publishers={}, batch_size=1, max_attempts=3, now=NOW
    )

    assert result.failures == (OutboxDispatchFailure(event_id, "unknown", "failed"),)
    stored = _stored(db_session, event_id)
    assert stored.status is OutboxEventStatus.FAILED
    assert stored.last_error == "No publisher is registered for this outbox event type."
    error = UnknownOutboxEventTypeError(event_id=event_id, event_type="unknown")
    assert (error.event_id, error.event_type) == (event_id, "unknown")


@pytest.mark.parametrize(
    "publisher_error",
    [RetryableOutboxPublishError("secret"), RuntimeError("credential=secret")],
)
def test_publisher_errors_are_requeued_without_raw_exception_text(
    db_session: Session,
    session_factory: Callable[[], Session],
    publisher_error: Exception,
) -> None:
    event_id = _event(db_session, "retry")

    def fail(payload: dict[str, object]) -> None:
        raise publisher_error

    result = dispatch_outbox_events(
        session_factory,
        publishers={"retry": fail},
        batch_size=1,
        max_attempts=3,
        now=NOW,
    )

    assert result == OutboxDispatchResult(
        1, 0, 1, 0, (OutboxDispatchFailure(event_id, "retry", "requeued"),)
    )
    stored = _stored(db_session, event_id)
    assert stored.status is OutboxEventStatus.PENDING
    assert stored.last_error == "Outbox publication failed and will be retried."


def test_permanent_publisher_error_fails_immediately_and_continues(
    db_session: Session, session_factory: Callable[[], Session]
) -> None:
    invalid_id = _event(db_session, "invalid")
    valid_id = _event(db_session, "valid")
    published: list[dict[str, object]] = []

    def reject(payload: dict[str, object]) -> None:
        raise PermanentOutboxPublishError("sensitive validation detail")

    result = dispatch_outbox_events(
        session_factory,
        publishers={"invalid": reject, "valid": published.append},
        batch_size=2,
        max_attempts=5,
        now=NOW,
    )

    assert result == OutboxDispatchResult(
        2,
        1,
        0,
        1,
        (OutboxDispatchFailure(invalid_id, "invalid", "failed"),),
    )
    invalid = _stored(db_session, invalid_id)
    assert invalid.status is OutboxEventStatus.FAILED
    assert invalid.last_error == "Outbox event payload is invalid."
    assert _stored(db_session, valid_id).status is OutboxEventStatus.PUBLISHED
    assert len(published) == 1


@pytest.mark.parametrize(
    ("previous_attempts", "delay_seconds"),
    [(0, 30), (1, 60), (7, 3600), (20, 3600)],
)
def test_retry_backoff_is_based_on_claimed_attempt_count(
    db_session: Session,
    session_factory: Callable[[], Session],
    previous_attempts: int,
    delay_seconds: int,
) -> None:
    event_id = _event(db_session, "backoff", attempt_count=previous_attempts)

    def fail(payload: dict[str, object]) -> None:
        raise RuntimeError

    dispatch_outbox_events(
        session_factory,
        publishers={"backoff": fail},
        batch_size=1,
        max_attempts=100,
        now=NOW,
    )

    available_at = _stored(db_session, event_id).available_at
    assert available_at.replace(tzinfo=UTC) == NOW + timedelta(seconds=delay_seconds)


def test_max_attempt_is_terminal_failure(
    db_session: Session, session_factory: Callable[[], Session]
) -> None:
    event_id = _event(db_session, "terminal", attempt_count=2)

    def fail(payload: dict[str, object]) -> None:
        raise RetryableOutboxPublishError

    result = dispatch_outbox_events(
        session_factory,
        publishers={"terminal": fail},
        batch_size=1,
        max_attempts=3,
        now=NOW,
    )

    assert result.failed_count == 1
    stored = _stored(db_session, event_id)
    assert stored.status is OutboxEventStatus.FAILED
    assert stored.last_error == "Outbox publication failed after maximum attempts."


def test_continues_after_failures_and_reports_mixed_counters(
    db_session: Session, session_factory: Callable[[], Session]
) -> None:
    retry_id = _event(db_session, "retry")
    unknown_id = _event(db_session, "unknown")
    success_id = _event(db_session, "success")
    calls: list[int] = []

    def retry(payload: dict[str, object]) -> None:
        raise RuntimeError

    result = dispatch_outbox_events(
        session_factory,
        publishers={"retry": retry, "success": lambda payload: calls.append(1)},
        batch_size=3,
        max_attempts=3,
        now=NOW,
    )

    assert calls == [1]
    assert result == OutboxDispatchResult(
        claimed_count=3,
        published_count=1,
        requeued_count=1,
        failed_count=1,
        failures=(
            OutboxDispatchFailure(retry_id, "retry", "requeued"),
            OutboxDispatchFailure(unknown_id, "unknown", "failed"),
        ),
    )
    assert _stored(db_session, success_id).status is OutboxEventStatus.PUBLISHED


def test_claim_commit_failure_rolls_back_closes_and_propagates(
    db_session: Session,
) -> None:
    _event(db_session, "claim-failure")
    factory = sessionmaker(
        bind=db_session.get_bind(), class_=TrackingSession, autoflush=False
    )
    session = factory()

    def fail_commit() -> None:
        raise SQLAlchemyError("claim commit failed")

    session.commit = fail_commit  # type: ignore[method-assign]

    with pytest.raises(SQLAlchemyError, match="claim commit failed"):
        dispatch_outbox_events(
            lambda: session,
            publishers={"claim-failure": lambda payload: None},
            batch_size=1,
            max_attempts=3,
            now=NOW,
        )

    assert session.rollback_count == 1
    assert session.was_closed


def test_final_commit_failure_is_not_treated_as_publisher_failure(
    db_session: Session,
) -> None:
    _event(db_session, "final-failure")
    factory = sessionmaker(
        bind=db_session.get_bind(), class_=TrackingSession, autoflush=False
    )
    sessions = [factory(), factory()]

    def fail_commit() -> None:
        raise SQLAlchemyError("final commit failed")

    sessions[1].commit = fail_commit  # type: ignore[method-assign]

    with pytest.raises(SQLAlchemyError, match="final commit failed"):
        dispatch_outbox_events(
            lambda: sessions.pop(0),
            publishers={"final-failure": lambda payload: None},
            batch_size=1,
            max_attempts=3,
            now=NOW,
        )

    final_session = TrackingSession.created[-1]
    assert final_session.rollback_count == 1
    assert final_session.was_closed


def test_missing_event_during_finalization_raises_identified_error(
    db_session: Session, session_factory: Callable[[], Session]
) -> None:
    event_id = _event(db_session, "vanishing")

    def remove_event(payload: dict[str, object]) -> None:
        with session_factory() as session:
            session.execute(delete(OutboxEvent).where(OutboxEvent.id == event_id))
            session.commit()

    with pytest.raises(OutboxEventNotFoundDuringDispatchError) as exc_info:
        dispatch_outbox_events(
            session_factory,
            publishers={"vanishing": remove_event},
            batch_size=1,
            max_attempts=3,
            now=NOW,
        )

    assert exc_info.value.event_id == event_id
    assert exc_info.value.event_type == "vanishing"


def test_no_dispatch_sessions_have_open_transactions_after_completion(
    db_session: Session, session_factory: Callable[[], Session]
) -> None:
    _event(db_session, "one")
    _event(db_session, "two")

    dispatch_outbox_events(
        session_factory,
        publishers={"one": lambda payload: None, "two": lambda payload: None},
        batch_size=2,
        max_attempts=3,
        now=NOW,
    )

    assert all(session.was_closed for session in TrackingSession.created)
    assert all(not session.in_transaction() for session in TrackingSession.created)
    assert db_session.scalar(select(OutboxEvent).limit(1)) is not None
