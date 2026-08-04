from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest

from app.storage import (
    ImportFileTooLargeError,
    InvalidImportStorageKeyError,
    LocalImportFileStorage,
)


def test_save_persists_bytes_and_returns_relative_storage_key(tmp_path: Path) -> None:
    storage = LocalImportFileStorage(root=tmp_path, max_size_bytes=32)
    payload = b"symbol,side\nAAPL,long\n"
    stream = BytesIO(payload)

    stored_file = storage.save(stream, user_id=42)

    saved_path = tmp_path / stored_file.storage_key
    assert stored_file.size_bytes == len(payload)
    assert stored_file.storage_key == saved_path.relative_to(tmp_path).as_posix()
    assert saved_path.read_bytes() == payload
    assert saved_path.parent == tmp_path / "imports" / "42"
    assert saved_path.suffix == ".csv"
    assert stream.closed is False


def test_save_generates_unique_keys_for_each_file(tmp_path: Path) -> None:
    storage = LocalImportFileStorage(root=tmp_path, max_size_bytes=32)

    first_file = storage.save(BytesIO(b"first"), user_id=7)
    second_file = storage.save(BytesIO(b"second"), user_id=7)

    assert first_file.storage_key != second_file.storage_key


def test_save_creates_missing_directories(tmp_path: Path) -> None:
    root = tmp_path / "nested" / "uploads"
    storage = LocalImportFileStorage(root=root, max_size_bytes=16)

    stored_file = storage.save(BytesIO(b"content"), user_id=11)

    assert (root / stored_file.storage_key).exists()


def test_save_accepts_file_exactly_at_size_limit(tmp_path: Path) -> None:
    payload = b"12345"
    storage = LocalImportFileStorage(root=tmp_path, max_size_bytes=len(payload))

    stored_file = storage.save(BytesIO(payload), user_id=3)

    assert stored_file.size_bytes == len(payload)
    assert (tmp_path / stored_file.storage_key).read_bytes() == payload


def test_save_rejects_oversized_file_without_partial_output(tmp_path: Path) -> None:
    storage = LocalImportFileStorage(root=tmp_path, max_size_bytes=4)

    with pytest.raises(ImportFileTooLargeError) as exc_info:
        storage.save(BytesIO(b"12345"), user_id=9)

    assert exc_info.value.max_size_bytes == 4
    assert exc_info.value.actual_size_bytes == 5
    assert not any(path.is_file() for path in tmp_path.rglob("*"))


def test_save_cleans_up_temporary_file_when_stream_read_fails(tmp_path: Path) -> None:
    storage = LocalImportFileStorage(root=tmp_path, max_size_bytes=16)

    class FailingStream:
        def __init__(self) -> None:
            self._reads = 0

        def read(self, _: int) -> bytes:
            self._reads += 1
            if self._reads == 1:
                return b"part"
            raise OSError("stream failure")

    with pytest.raises(OSError, match="stream failure"):
        storage.save(FailingStream(), user_id=5)

    assert not any(path.is_file() for path in tmp_path.rglob("*"))


def test_open_text_reads_utf8_text_and_closes_after_context_exit(
    tmp_path: Path,
) -> None:
    storage = LocalImportFileStorage(root=tmp_path, max_size_bytes=32)
    stored_file = storage.save(BytesIO(b"col1,col2\r\nx,y\r\n"), user_id=8)

    with storage.open_text(stored_file.storage_key) as file_obj:
        contents = file_obj.read()
        assert file_obj.closed is False

    assert contents == "col1,col2\r\nx,y\r\n"
    assert file_obj.closed is True


def test_open_text_raises_file_not_found_for_missing_file(tmp_path: Path) -> None:
    storage = LocalImportFileStorage(root=tmp_path, max_size_bytes=16)

    with pytest.raises(FileNotFoundError):
        with storage.open_text("imports/1/missing.csv"):
            pass


def test_delete_removes_existing_file_and_reports_missing_files(tmp_path: Path) -> None:
    storage = LocalImportFileStorage(root=tmp_path, max_size_bytes=16)
    stored_file = storage.save(BytesIO(b"gone"), user_id=4)
    saved_path = tmp_path / stored_file.storage_key

    assert storage.delete(stored_file.storage_key) is True
    assert saved_path.exists() is False
    assert storage.delete(stored_file.storage_key) is False


@pytest.mark.parametrize(
    "storage_key",
    [
        "../outside.csv",
        "imports/2/../../outside.csv",
    ],
)
def test_storage_rejects_parent_directory_traversal(
    tmp_path: Path,
    storage_key: str,
) -> None:
    storage = LocalImportFileStorage(root=tmp_path, max_size_bytes=16)

    with pytest.raises(InvalidImportStorageKeyError):
        storage.open_text(storage_key)

    with pytest.raises(InvalidImportStorageKeyError):
        storage.delete(storage_key)


def test_storage_rejects_absolute_storage_keys(tmp_path: Path) -> None:
    storage = LocalImportFileStorage(root=tmp_path, max_size_bytes=16)
    absolute_key = str((tmp_path / "imports" / "1" / "file.csv").resolve())

    with pytest.raises(InvalidImportStorageKeyError):
        storage.open_text(absolute_key)

    with pytest.raises(InvalidImportStorageKeyError):
        storage.delete(absolute_key)


@pytest.mark.parametrize("invalid_user_id", [0, -1])
def test_save_rejects_non_positive_user_ids(
    tmp_path: Path,
    invalid_user_id: int,
) -> None:
    storage = LocalImportFileStorage(root=tmp_path, max_size_bytes=16)

    with pytest.raises(ValueError, match="user_id"):
        storage.save(BytesIO(b"data"), user_id=invalid_user_id)


@pytest.mark.parametrize("invalid_max_size_bytes", [0, -1])
def test_storage_rejects_non_positive_maximum_size(invalid_max_size_bytes: int) -> None:
    with pytest.raises(ValueError, match="max_size_bytes"):
        LocalImportFileStorage(
            root=Path("uploads"),
            max_size_bytes=invalid_max_size_bytes,
        )
