from types import SimpleNamespace

import pytest

from app.events.publishers import (
    OUTBOX_PUBLISHERS,
    publish_trade_import_requested,
)
from app.events.types import TRADE_IMPORT_REQUESTED_EVENT
from app.services.outbox_dispatcher import PermanentOutboxPublishError


def test_registry_explicitly_maps_trade_import_event_to_publisher() -> None:
    assert OUTBOX_PUBLISHERS == {
        TRADE_IMPORT_REQUESTED_EVENT: publish_trade_import_requested
    }


def test_trade_import_publisher_delays_task_and_returns_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delay_result = object()
    calls: list[int] = []

    def delay(import_job_id: int) -> object:
        calls.append(import_job_id)
        return delay_result

    monkeypatch.setattr(
        "app.tasks.imports.process_trade_import_task",
        SimpleNamespace(delay=delay),
    )

    result = publish_trade_import_requested({"import_job_id": 42})

    assert result is delay_result
    assert calls == [42]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"import_job_id": 1, "extra": True},
        {"import_job_id": True},
        {"import_job_id": 1.0},
        {"import_job_id": "1"},
        {"import_job_id": 0},
        {"import_job_id": -1},
        {"ImportJobId": 1},
    ],
)
def test_trade_import_publisher_rejects_invalid_payload_without_delay(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]
) -> None:
    delay_calls: list[object] = []
    monkeypatch.setattr(
        "app.tasks.imports.process_trade_import_task",
        SimpleNamespace(delay=delay_calls.append),
    )

    with pytest.raises(PermanentOutboxPublishError):
        publish_trade_import_requested(payload)

    assert delay_calls == []
