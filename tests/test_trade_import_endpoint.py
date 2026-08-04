from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_import_file_storage
from app.main import app
from app.models.import_job import ImportJob, ImportJobStatus
from app.storage import LocalImportFileStorage
from tests.helpers import assert_datetime_equal, auth_headers, register_and_login

IMPORT_JOB_RESPONSE_FIELDS = {
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


def create_import_job_in_db(
    db_session: Session,
    *,
    user_id: int,
    sequence: int,
    status: ImportJobStatus = ImportJobStatus.PENDING,
    created_at: datetime | None = None,
    total_rows: int | None = None,
    imported_rows: int = 0,
    rejected_rows: int = 0,
    failure_message: str | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> ImportJob:
    import_job = ImportJob(
        user_id=user_id,
        status=status,
        original_filename=f"trades-{sequence}.csv",
        storage_key=f"internal/{user_id}/{sequence}.csv",
        total_rows=total_rows,
        imported_rows=imported_rows,
        rejected_rows=rejected_rows,
        failure_message=failure_message,
        started_at=started_at,
        completed_at=completed_at,
    )
    if created_at is not None:
        import_job.created_at = created_at
        import_job.updated_at = created_at
    db_session.add(import_job)
    db_session.commit()
    db_session.refresh(import_job)
    return import_job


@pytest.mark.parametrize("path", ["/trade-imports", "/trade-imports/1"])
def test_read_trade_import_endpoints_require_authentication(
    client: TestClient,
    path: str,
) -> None:
    response = client.get(path)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    ("job_status", "total_rows", "imported_rows", "rejected_rows", "failure_message"),
    [
        (ImportJobStatus.PENDING, None, 0, 0, None),
        (ImportJobStatus.PROCESSING, 12, 4, 1, None),
        (ImportJobStatus.COMPLETED, 12, 10, 2, None),
        (ImportJobStatus.FAILED, 12, 4, 1, "Some rows could not be imported."),
    ],
)
def test_get_trade_import_returns_owner_job_status_counters_and_timestamps(
    client: TestClient,
    db_session: Session,
    job_status: ImportJobStatus,
    total_rows: int | None,
    imported_rows: int,
    rejected_rows: int,
    failure_message: str | None,
) -> None:
    access_token, user_id = register_and_login(client)
    started_at = datetime(2026, 8, 4, 9, 30, tzinfo=UTC)
    completed_at = (
        datetime(2026, 8, 4, 9, 35, tzinfo=UTC)
        if job_status in {ImportJobStatus.COMPLETED, ImportJobStatus.FAILED}
        else None
    )
    import_job = create_import_job_in_db(
        db_session,
        user_id=user_id,
        sequence=1,
        status=job_status,
        total_rows=total_rows,
        imported_rows=imported_rows,
        rejected_rows=rejected_rows,
        failure_message=failure_message,
        started_at=started_at if job_status is not ImportJobStatus.PENDING else None,
        completed_at=completed_at,
    )

    response = client.get(
        f"/trade-imports/{import_job.id}",
        headers=auth_headers(access_token),
    )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == IMPORT_JOB_RESPONSE_FIELDS
    assert payload["id"] == import_job.id
    assert payload["status"] == job_status.value
    assert payload["original_filename"] == "trades-1.csv"
    assert payload["total_rows"] == total_rows
    assert payload["imported_rows"] == imported_rows
    assert payload["rejected_rows"] == rejected_rows
    assert payload["failure_message"] == failure_message
    assert_datetime_equal(payload["started_at"], import_job.started_at)
    assert_datetime_equal(payload["completed_at"], import_job.completed_at)
    assert_datetime_equal(payload["created_at"], import_job.created_at)
    assert_datetime_equal(payload["updated_at"], import_job.updated_at)
    assert "storage_key" not in payload
    assert "user_id" not in payload
    assert "task_id" not in payload


def test_get_trade_import_returns_404_for_missing_job(
    client: TestClient,
) -> None:
    access_token, _ = register_and_login(client)

    response = client.get("/trade-imports/999999", headers=auth_headers(access_token))

    assert response.status_code == 404
    assert response.json() == {"detail": "Trade import job not found."}


def test_get_trade_import_returns_404_for_foreign_job_without_ownership_leak(
    client: TestClient,
    db_session: Session,
) -> None:
    owner_token, owner_id = register_and_login(client, email="owner@example.com")
    other_token, _ = register_and_login(client, email="other@example.com")
    import_job = create_import_job_in_db(
        db_session,
        user_id=owner_id,
        sequence=1,
        failure_message="Owner-visible safe failure.",
    )

    foreign_response = client.get(
        f"/trade-imports/{import_job.id}",
        headers=auth_headers(other_token),
    )
    missing_response = client.get(
        "/trade-imports/999999",
        headers=auth_headers(other_token),
    )

    assert foreign_response.status_code == 404
    assert foreign_response.json() == {"detail": "Trade import job not found."}
    assert foreign_response.json() == missing_response.json()
    assert "Owner-visible" not in foreign_response.text
    assert (
        client.get(
            f"/trade-imports/{import_job.id}",
            headers=auth_headers(owner_token),
        ).status_code
        == 200
    )


def test_list_trade_imports_returns_only_owner_jobs_in_repository_order(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, user_id = register_and_login(client, email="owner@example.com")
    _, other_user_id = register_and_login(client, email="other@example.com")
    base_time = datetime(2026, 8, 4, 9, 0, tzinfo=UTC)
    older = create_import_job_in_db(
        db_session, user_id=user_id, sequence=1, created_at=base_time
    )
    newest_lower_id = create_import_job_in_db(
        db_session,
        user_id=user_id,
        sequence=2,
        created_at=base_time + timedelta(minutes=1),
    )
    newest_higher_id = create_import_job_in_db(
        db_session,
        user_id=user_id,
        sequence=3,
        created_at=base_time + timedelta(minutes=1),
    )
    foreign = create_import_job_in_db(
        db_session,
        user_id=other_user_id,
        sequence=4,
        created_at=base_time + timedelta(minutes=2),
    )

    response = client.get("/trade-imports", headers=auth_headers(access_token))

    assert response.status_code == 200
    payload = response.json()
    assert [job["id"] for job in payload] == [
        newest_higher_id.id,
        newest_lower_id.id,
        older.id,
    ]
    assert foreign.id not in {job["id"] for job in payload}
    assert all(set(job) == IMPORT_JOB_RESPONSE_FIELDS for job in payload)
    assert all("storage_key" not in job for job in payload)
    assert all("user_id" not in job for job in payload)
    assert all("task_id" not in job for job in payload)


def test_list_trade_imports_uses_default_limit_of_twenty(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, user_id = register_and_login(client)
    for sequence in range(21):
        create_import_job_in_db(db_session, user_id=user_id, sequence=sequence)

    response = client.get("/trade-imports", headers=auth_headers(access_token))

    assert response.status_code == 200
    assert len(response.json()) == 20


def test_list_trade_imports_supports_custom_limit_and_offset(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, user_id = register_and_login(client)
    jobs = [
        create_import_job_in_db(db_session, user_id=user_id, sequence=sequence)
        for sequence in range(5)
    ]

    limited_response = client.get(
        "/trade-imports?limit=2", headers=auth_headers(access_token)
    )
    offset_response = client.get(
        "/trade-imports?limit=2&offset=2", headers=auth_headers(access_token)
    )

    assert [job["id"] for job in limited_response.json()] == [jobs[4].id, jobs[3].id]
    assert [job["id"] for job in offset_response.json()] == [jobs[2].id, jobs[1].id]


def test_list_trade_imports_returns_empty_list_when_owner_has_no_jobs(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, _ = register_and_login(client, email="owner@example.com")
    _, other_user_id = register_and_login(client, email="other@example.com")
    create_import_job_in_db(db_session, user_id=other_user_id, sequence=1)

    response = client.get("/trade-imports", headers=auth_headers(access_token))

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    "query",
    ["limit=0", "limit=101", "offset=-1"],
)
def test_list_trade_imports_rejects_invalid_pagination(
    client: TestClient,
    query: str,
) -> None:
    access_token, _ = register_and_login(client)

    response = client.get(f"/trade-imports?{query}", headers=auth_headers(access_token))

    assert response.status_code == 422


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
