from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.outbox_event import OutboxEvent, OutboxEventStatus


def test_outbox_event_persists_fields_and_json(db_session: Session) -> None:
    available_at = datetime(2026, 8, 4, 10, 0, tzinfo=UTC)
    event = OutboxEvent(
        event_type="trade.created",
        payload={"trade_id": 42, "tags": ["swing", "reviewed"]},
        available_at=available_at,
    )
    db_session.add(event)
    db_session.commit()

    stored = db_session.scalar(select(OutboxEvent).where(OutboxEvent.id == event.id))

    assert stored is not None
    assert stored.event_type == "trade.created"
    assert stored.payload == {"trade_id": 42, "tags": ["swing", "reviewed"]}
    assert stored.available_at.replace(tzinfo=UTC) == available_at
    assert stored.created_at is not None
    assert stored.updated_at is not None


def test_outbox_event_defaults_are_applied(db_session: Session) -> None:
    before = datetime.now(UTC)
    event = OutboxEvent(event_type="trade.updated", payload={"trade_id": 7})
    db_session.add(event)
    db_session.commit()
    after = datetime.now(UTC)

    assert event.status is OutboxEventStatus.PENDING
    assert event.attempt_count == 0
    assert event.last_error is None
    assert event.claimed_at is None
    assert event.published_at is None
    assert before <= event.available_at.replace(tzinfo=UTC) <= after


@pytest.mark.parametrize(
    "event",
    [
        OutboxEvent(event_type="counter.invalid", payload={}, attempt_count=-1),
        OutboxEvent(event_type="   ", payload={}),
        OutboxEvent(
            event_type="publish.invalid",
            payload={},
            status=OutboxEventStatus.PUBLISHED,
        ),
    ],
)
def test_outbox_event_constraints_reject_invalid_rows(
    db_session: Session,
    event: OutboxEvent,
) -> None:
    db_session.add(event)

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()
