from types import SimpleNamespace

import pytest

from app.services.outbox_dispatcher import OutboxDispatchResult
from app.services.outbox_recovery import OutboxRecoveryResult
from app.tasks.outbox import dispatch_outbox_events_task


def test_dispatch_task_uses_config_registry_and_logs_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = object()
    publishers = {"event": lambda payload: None}
    result = OutboxDispatchResult(4, 1, 2, 1, ())
    recovery_result = OutboxRecoveryResult(3, 2, 1, (1, 2, 3))
    calls: list[tuple[object, object, int, int]] = []
    order: list[str] = []
    info_calls: list[tuple[object, ...]] = []

    def dispatch(
        factory: object,
        *,
        publishers: object,
        batch_size: int,
        max_attempts: int,
    ) -> OutboxDispatchResult:
        order.append("dispatch")
        calls.append((factory, publishers, batch_size, max_attempts))
        return result

    def recover(
        factory: object,
        *,
        batch_size: int,
        max_attempts: int,
        processing_timeout_seconds: int,
    ) -> OutboxRecoveryResult:
        order.append("recover")
        assert (factory, batch_size, max_attempts, processing_timeout_seconds) == (
            session_factory,
            50,
            5,
            300,
        )
        return recovery_result

    monkeypatch.setattr("app.tasks.outbox.SessionLocal", session_factory)
    monkeypatch.setattr("app.tasks.outbox.OUTBOX_PUBLISHERS", publishers)
    monkeypatch.setattr(
        "app.tasks.outbox.settings",
        SimpleNamespace(
            outbox_dispatch_batch_size=50,
            outbox_dispatch_max_attempts=5,
            outbox_processing_timeout_seconds=300,
        ),
    )
    monkeypatch.setattr("app.tasks.outbox.recover_stale_outbox_events", recover)
    monkeypatch.setattr("app.tasks.outbox.dispatch_outbox_events", dispatch)
    monkeypatch.setattr(
        "app.tasks.outbox.logger",
        SimpleNamespace(info=lambda *args: info_calls.append(args)),
    )

    task_result = dispatch_outbox_events_task()

    assert task_result is None
    assert calls == [(session_factory, publishers, 50, 5)]
    assert order == ["recover", "dispatch"]
    assert info_calls[0][1:] == (3, 2, 1)
    assert info_calls[1][1:] == (4, 1, 2, 1)
    assert all(
        name in info_calls[1][0]
        for name in (
            "claimed_count",
            "published_count",
            "requeued_count",
            "failed_count",
        )
    )


def test_dispatch_task_logs_and_reraises_infrastructure_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = RuntimeError("database unavailable")
    exception_calls: list[str] = []

    def fail(*args: object, **kwargs: object) -> None:
        raise failure

    monkeypatch.setattr(
        "app.tasks.outbox.recover_stale_outbox_events",
        lambda *args, **kwargs: OutboxRecoveryResult(0, 0, 0, ()),
    )

    monkeypatch.setattr("app.tasks.outbox.dispatch_outbox_events", fail)
    monkeypatch.setattr(
        "app.tasks.outbox.logger",
        SimpleNamespace(info=lambda *args: None, exception=exception_calls.append),
    )

    with pytest.raises(RuntimeError) as exc_info:
        dispatch_outbox_events_task()

    assert exc_info.value is failure
    assert exception_calls == ["Outbox dispatcher task failed."]


def test_dispatch_task_does_not_dispatch_when_recovery_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = RuntimeError("recovery failed")
    dispatch_calls: list[object] = []
    exception_calls: list[str] = []

    def fail_recovery(*args: object, **kwargs: object) -> None:
        raise failure

    monkeypatch.setattr("app.tasks.outbox.recover_stale_outbox_events", fail_recovery)
    monkeypatch.setattr(
        "app.tasks.outbox.dispatch_outbox_events",
        lambda *args, **kwargs: dispatch_calls.append(args),
    )
    monkeypatch.setattr(
        "app.tasks.outbox.logger",
        SimpleNamespace(exception=exception_calls.append),
    )

    with pytest.raises(RuntimeError) as exc_info:
        dispatch_outbox_events_task()

    assert exc_info.value is failure
    assert dispatch_calls == []
    assert exception_calls == ["Outbox recovery failed."]
