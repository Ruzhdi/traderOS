from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models.outbox_event import OutboxEvent, OutboxEventStatus
from app.repositories.outbox_event import add_outbox_event
from app.services.outbox_recovery import (
    OutboxRecoveryResult,
    recover_stale_outbox_events,
)


def _processing_event(
    db_session: Session,
    *,
    event_type: str,
    claimed_at: datetime | None,
    attempt_count: int,
) -> OutboxEvent:
    event = add_outbox_event(db_session, event_type=event_type, payload={})
    event.status = OutboxEventStatus.PROCESSING
    event.claimed_at = claimed_at
    event.attempt_count = attempt_count
    db_session.commit()
    return event


def test_recovery_requeues_stale_and_null_claims_and_fails_terminal_events(
    db_session: Session,
) -> None:
    now = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    requeued = _processing_event(
        db_session,
        event_type="requeued",
        claimed_at=now - timedelta(minutes=10),
        attempt_count=2,
    )
    null_claim = _processing_event(
        db_session,
        event_type="null-claim",
        claimed_at=None,
        attempt_count=1,
    )
    terminal = _processing_event(
        db_session,
        event_type="terminal",
        claimed_at=now - timedelta(minutes=6),
        attempt_count=5,
    )
    recent = _processing_event(
        db_session,
        event_type="recent",
        claimed_at=now - timedelta(minutes=1),
        attempt_count=1,
    )
    requeued_id = requeued.id
    null_claim_id = null_claim.id
    terminal_id = terminal.id
    recent_id = recent.id

    result = recover_stale_outbox_events(
        lambda: db_session,
        batch_size=10,
        max_attempts=5,
        processing_timeout_seconds=300,
        now=now,
    )

    assert result == OutboxRecoveryResult(
        recovered_count=3,
        requeued_count=2,
        failed_count=1,
        event_ids=(null_claim_id, requeued_id, terminal_id),
    )
    requeued = db_session.get_one(OutboxEvent, requeued_id)
    null_claim = db_session.get_one(OutboxEvent, null_claim_id)
    terminal = db_session.get_one(OutboxEvent, terminal_id)
    recent = db_session.get_one(OutboxEvent, recent_id)
    assert requeued.status is OutboxEventStatus.PENDING
    assert requeued.available_at.replace(tzinfo=UTC) == now
    assert requeued.claimed_at is None
    assert requeued.last_error == "Stale outbox processing claim was recovered."
    assert requeued.attempt_count == 2
    assert null_claim.status is OutboxEventStatus.PENDING
    assert terminal.status is OutboxEventStatus.FAILED
    assert terminal.last_error == (
        "Stale outbox event exceeded maximum processing attempts."
    )
    assert terminal.attempt_count == 5
    assert recent.status is OutboxEventStatus.PROCESSING


def test_recovery_commits_once_and_always_closes(db_session: Session) -> None:
    calls: list[str] = []
    original_commit = db_session.commit
    original_close = db_session.close
    db_session.commit = lambda: (calls.append("commit"), original_commit())[1]
    db_session.close = lambda: calls.append("close")
    try:
        result = recover_stale_outbox_events(
            lambda: db_session,
            batch_size=10,
            max_attempts=5,
            processing_timeout_seconds=300,
            now=datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
        )
    finally:
        db_session.commit = original_commit
        db_session.close = original_close

    assert result == OutboxRecoveryResult(0, 0, 0, ())
    assert calls == ["commit", "close"]


def test_recovery_rolls_back_closes_and_reraises_infrastructure_error(
    db_session: Session,
) -> None:
    failure = RuntimeError("database unavailable")
    calls: list[str] = []
    original_commit = db_session.commit
    original_rollback = db_session.rollback
    original_close = db_session.close
    db_session.commit = lambda: (_ for _ in ()).throw(failure)
    db_session.rollback = lambda: calls.append("rollback")
    db_session.close = lambda: calls.append("close")
    try:
        with pytest.raises(RuntimeError) as exc_info:
            recover_stale_outbox_events(
                lambda: db_session,
                batch_size=10,
                max_attempts=5,
                processing_timeout_seconds=300,
            )
    finally:
        db_session.commit = original_commit
        db_session.rollback = original_rollback
        db_session.close = original_close

    assert exc_info.value is failure
    assert calls == ["rollback", "close"]


def test_recovery_result_enforces_counter_invariant() -> None:
    with pytest.raises(ValueError, match="recovered_count must equal"):
        OutboxRecoveryResult(2, 0, 1, ())
