from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_import_file_storage
from app.main import app
from app.models.import_job import ImportJob, ImportJobStatus
from app.storage import LocalImportFileStorage
from tests.helpers import auth_headers, register_and_login


def test_create_trade_import_requires_authentication(client: TestClient) -> None:
    response = client.post(
        "/trade-imports",
        files={"file": ("trades.csv", b"symbol,side\nAAPL,long\n", "text/csv")},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_create_trade_import_returns_pending_job_and_persists_upload(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    access_token, user_id = register_and_login(client)
    storage = LocalImportFileStorage(root=tmp_path, max_size_bytes=1024)
    task_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    payload = (
        b"symbol,side,entry_price,quantity,opened_at\n"
        b"AAPL,long,192.50,10,2026-08-04T09:30:00Z\n"
    )
    app.dependency_overrides[get_import_file_storage] = lambda: storage

    def fake_delay(*args, **kwargs) -> None:
        task_calls.append((args, kwargs))

    monkeypatch.setattr(
        "app.api.routes.trade_imports.process_trade_import_task.delay",
        fake_delay,
    )

    response = client.post(
        "/trade-imports",
        files={"file": (" reports\\2026\\trades.CSV ", payload, "text/csv")},
        headers=auth_headers(access_token),
    )

    assert response.status_code == 202

    response_payload = response.json()
    import_job = db_session.scalar(
        select(ImportJob).where(ImportJob.id == response_payload["id"])
    )

    assert set(response_payload) == {
        "id",
        "status",
        "original_filename",
        "total_rows",
        "imported_rows",
        "rejected_rows",
        "failure_message",
        "started_at",
        "completed_at",
        "created_at",
        "updated_at",
    }
    assert response_payload["status"] == "pending"
    assert response_payload["original_filename"] == "trades.CSV"
    assert response_payload["total_rows"] is None
    assert response_payload["imported_rows"] == 0
    assert response_payload["rejected_rows"] == 0
    assert response_payload["failure_message"] is None
    assert response_payload["started_at"] is None
    assert response_payload["completed_at"] is None
    assert response_payload["created_at"]
    assert response_payload["updated_at"]
    assert "storage_key" not in response_payload
    assert "task_id" not in response_payload
    assert "user_id" not in response_payload
    assert import_job is not None
    assert import_job.user_id == user_id
    assert import_job.status is ImportJobStatus.PENDING
    assert import_job.original_filename == "trades.CSV"
    assert (tmp_path / import_job.storage_key).read_bytes() == payload
    assert task_calls == [((import_job.id,), {})]


@pytest.mark.parametrize(
    ("filename", "expected_status_code", "expected_body"),
    [
        (
            "",
            422,
            {
                "detail": [
                    {
                        "type": "value_error",
                        "loc": ["body", "file"],
                        "msg": (
                            "Value error, Expected UploadFile, received: <class 'str'>"
                        ),
                        "input": "symbol,side\nAAPL,long\n",
                        "ctx": {
                            "error": {},
                        },
                    }
                ]
            },
        ),
        ("trades.txt", 400, {"detail": "Import filename is invalid."}),
        ("trades.csv.exe", 400, {"detail": "Import filename is invalid."}),
        ((("a" * 256) + ".csv"), 400, {"detail": "Import filename is invalid."}),
    ],
)
def test_create_trade_import_rejects_invalid_filenames_without_side_effects(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    filename: str,
    expected_status_code: int,
    expected_body: dict[str, object],
) -> None:
    access_token, _ = register_and_login(client)
    storage = LocalImportFileStorage(root=tmp_path, max_size_bytes=1024)
    task_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    app.dependency_overrides[get_import_file_storage] = lambda: storage

    def fake_delay(*args, **kwargs) -> None:
        task_calls.append((args, kwargs))

    monkeypatch.setattr(
        "app.api.routes.trade_imports.process_trade_import_task.delay",
        fake_delay,
    )

    response = client.post(
        "/trade-imports",
        files={"file": (filename, b"symbol,side\nAAPL,long\n", "text/csv")},
        headers=auth_headers(access_token),
    )

    assert response.status_code == expected_status_code
    response_body = response.json()
    if expected_status_code == 422:
        response_body["detail"][0].pop("url", None)
    assert response_body == expected_body
    assert db_session.scalars(select(ImportJob)).all() == []
    assert not any(path.is_file() for path in tmp_path.rglob("*"))
    assert task_calls == []


def test_create_trade_import_returns_413_for_oversized_upload(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    access_token, _ = register_and_login(client)
    storage = LocalImportFileStorage(root=tmp_path, max_size_bytes=4)
    task_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    app.dependency_overrides[get_import_file_storage] = lambda: storage

    def fake_delay(*args, **kwargs) -> None:
        task_calls.append((args, kwargs))

    monkeypatch.setattr(
        "app.api.routes.trade_imports.process_trade_import_task.delay",
        fake_delay,
    )

    response = client.post(
        "/trade-imports",
        files={"file": ("trades.csv", b"12345", "text/csv")},
        headers=auth_headers(access_token),
    )

    assert response.status_code == 413
    assert db_session.scalars(select(ImportJob)).all() == []
    assert not any(path.is_file() for path in tmp_path.rglob("*"))
    assert task_calls == []


def test_create_trade_import_returns_503_when_enqueue_fails(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    access_token, user_id = register_and_login(client)
    storage = LocalImportFileStorage(root=tmp_path, max_size_bytes=1024)
    broker_error = RuntimeError("redis://user:secret@broker:6379/0 unavailable")
    payload = b"symbol,side\nAAPL,long\n"
    app.dependency_overrides[get_import_file_storage] = lambda: storage

    def failing_delay(*args, **kwargs) -> None:
        raise broker_error

    monkeypatch.setattr(
        "app.api.routes.trade_imports.process_trade_import_task.delay",
        failing_delay,
    )

    response = client.post(
        "/trade-imports",
        files={"file": ("trades.csv", payload, "text/csv")},
        headers=auth_headers(access_token),
    )

    jobs = db_session.scalars(select(ImportJob)).all()

    assert response.status_code == 503
    assert response.json() == {"detail": "Import could not be queued for processing."}
    assert "redis://" not in response.text
    assert len(jobs) == 1

    import_job = jobs[0]
    assert import_job.user_id == user_id
    assert import_job.status is ImportJobStatus.FAILED
    assert import_job.failure_message == "Import could not be queued for processing."
    assert (tmp_path / import_job.storage_key).exists() is False
