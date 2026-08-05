from types import SimpleNamespace

import pytest

from app.services.outbox_dispatcher import OutboxDispatchResult
from app.tasks.outbox import dispatch_outbox_events_task


def test_dispatch_task_uses_config_registry_and_logs_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = object()
    publishers = {"event": lambda payload: None}
    result = OutboxDispatchResult(4, 1, 2, 1, ())
    calls: list[tuple[object, object, int, int]] = []
    info_calls: list[tuple[object, ...]] = []

    def dispatch(
        factory: object,
        *,
        publishers: object,
        batch_size: int,
        max_attempts: int,
    ) -> OutboxDispatchResult:
        calls.append((factory, publishers, batch_size, max_attempts))
        return result

    monkeypatch.setattr("app.tasks.outbox.SessionLocal", session_factory)
    monkeypatch.setattr("app.tasks.outbox.OUTBOX_PUBLISHERS", publishers)
    monkeypatch.setattr(
        "app.tasks.outbox.settings",
        SimpleNamespace(
            outbox_dispatch_batch_size=50,
            outbox_dispatch_max_attempts=5,
        ),
    )
    monkeypatch.setattr("app.tasks.outbox.dispatch_outbox_events", dispatch)
    monkeypatch.setattr(
        "app.tasks.outbox.logger",
        SimpleNamespace(info=lambda *args: info_calls.append(args)),
    )

    task_result = dispatch_outbox_events_task()

    assert task_result is None
    assert calls == [(session_factory, publishers, 50, 5)]
    assert info_calls[0][1:] == (4, 1, 2, 1)
    assert all(
        name in info_calls[0][0]
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

    monkeypatch.setattr("app.tasks.outbox.dispatch_outbox_events", fail)
    monkeypatch.setattr(
        "app.tasks.outbox.logger",
        SimpleNamespace(exception=exception_calls.append),
    )

    with pytest.raises(RuntimeError) as exc_info:
        dispatch_outbox_events_task()

    assert exc_info.value is failure
    assert exception_calls == ["Outbox dispatcher task failed."]
