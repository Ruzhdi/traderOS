from collections.abc import Callable, Generator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.models.outbox_event import OutboxEvent, OutboxEventStatus
from app.repositories.outbox_event import add_outbox_event
from app.services.outbox_cleanup import (
    OutboxCleanupResult,
    cleanup_terminal_outbox_events,
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
        bind=db_session.get_bind(), class_=TrackingSession, autoflush=False
    )
    yield factory
    for session in TrackingSession.created:
        session.close()


def _terminal_event(
    db_session: Session,
    event_type: str,
    status: OutboxEventStatus,
    timestamp: datetime | None,
) -> int:
    event = add_outbox_event(db_session, event_type=event_type, payload={})
    event.status = status
    if status is OutboxEventStatus.PUBLISHED:
        event.published_at = timestamp
    else:
        event.updated_at = timestamp
    db_session.commit()
    return event.id


def test_cleanup_deletes_expired_terminal_events_and_preserves_others(
    db_session: Session, session_factory: Callable[[], Session]
) -> None:
    old_published = _terminal_event(
        db_session,
        "old-published",
        OutboxEventStatus.PUBLISHED,
        NOW - timedelta(days=8),
    )
    old_failed = _terminal_event(
        db_session, "old-failed", OutboxEventStatus.FAILED, NOW - timedelta(days=31)
    )
    recent_published = _terminal_event(
        db_session,
        "recent-published",
        OutboxEventStatus.PUBLISHED,
        NOW - timedelta(days=1),
    )
    recent_failed = _terminal_event(
        db_session, "recent-failed", OutboxEventStatus.FAILED, NOW - timedelta(days=1)
    )
    null_published_event = add_outbox_event(
        db_session, event_type="null-published", payload={}
    )
    null_published_event.published_at = None
    db_session.commit()
    null_published = null_published_event.id
    pending = add_outbox_event(db_session, event_type="pending", payload={})
    processing = add_outbox_event(db_session, event_type="processing", payload={})
    processing.status = OutboxEventStatus.PROCESSING
    db_session.commit()

    result = cleanup_terminal_outbox_events(
        session_factory,
        batch_size=10,
        published_retention_days=7,
        failed_retention_days=30,
        now=NOW,
    )

    assert result == OutboxCleanupResult(2, 1, 1, (old_failed, old_published))
    db_session.expire_all()
    assert db_session.get(OutboxEvent, old_published) is None
    assert db_session.get(OutboxEvent, old_failed) is None
    for event_id in (
        recent_published,
        recent_failed,
        null_published,
        pending.id,
        processing.id,
    ):
        assert db_session.get(OutboxEvent, event_id) is not None


def test_cleanup_is_deterministic_and_bounded(
    db_session: Session, session_factory: Callable[[], Session]
) -> None:
    oldest = _terminal_event(
        db_session, "oldest", OutboxEventStatus.FAILED, NOW - timedelta(days=50)
    )
    tied_first = _terminal_event(
        db_session, "tied-first", OutboxEventStatus.PUBLISHED, NOW - timedelta(days=40)
    )
    tied_second = _terminal_event(
        db_session, "tied-second", OutboxEventStatus.PUBLISHED, NOW - timedelta(days=40)
    )

    result = cleanup_terminal_outbox_events(
        session_factory,
        batch_size=2,
        published_retention_days=7,
        failed_retention_days=30,
        now=NOW,
    )

    assert result.event_ids == (oldest, tied_first)
    db_session.expire_all()
    assert db_session.get(OutboxEvent, tied_second) is not None


def test_cleanup_commits_once_and_closes(
    session_factory: Callable[[], Session],
) -> None:
    result = cleanup_terminal_outbox_events(
        session_factory,
        batch_size=10,
        published_retention_days=7,
        failed_retention_days=30,
        now=NOW,
    )

    assert result == OutboxCleanupResult(0, 0, 0, ())
    assert len(TrackingSession.created) == 1
    assert TrackingSession.created[0].commit_count == 1
    assert TrackingSession.created[0].was_closed


def test_cleanup_rolls_back_closes_and_reraises_commit_failure(
    db_session: Session,
) -> None:
    session = TrackingSession(bind=db_session.get_bind(), autoflush=False)
    failure = RuntimeError("database unavailable")
    session.commit = lambda: (_ for _ in ()).throw(failure)  # type: ignore[method-assign]

    with pytest.raises(RuntimeError) as exc_info:
        cleanup_terminal_outbox_events(
            lambda: session,
            batch_size=10,
            published_retention_days=7,
            failed_retention_days=30,
            now=NOW,
        )

    assert exc_info.value is failure
    assert session.rollback_count == 1
    assert session.was_closed


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"batch_size": 0}, "batch_size"),
        ({"published_retention_days": 0}, "published_retention_days"),
        ({"failed_retention_days": 0}, "failed_retention_days"),
    ],
)
def test_cleanup_rejects_non_positive_configuration(
    session_factory: Callable[[], Session], kwargs: dict[str, int], message: str
) -> None:
    arguments = {
        "batch_size": 10,
        "published_retention_days": 7,
        "failed_retention_days": 30,
        **kwargs,
    }
    with pytest.raises(ValueError, match=message):
        cleanup_terminal_outbox_events(session_factory, now=NOW, **arguments)


def test_cleanup_rejects_naive_now(session_factory: Callable[[], Session]) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        cleanup_terminal_outbox_events(
            session_factory,
            batch_size=10,
            published_retention_days=7,
            failed_retention_days=30,
            now=datetime(2026, 8, 4),
        )


def test_cleanup_result_enforces_invariants() -> None:
    with pytest.raises(ValueError, match="published_deleted_count"):
        OutboxCleanupResult(2, 0, 1, (1, 2))
    with pytest.raises(ValueError, match="number of event_ids"):
        OutboxCleanupResult(1, 1, 0, ())
