from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, TextIO
from uuid import uuid4

CHUNK_SIZE_BYTES = 64 * 1024


@dataclass(frozen=True)
class StoredImportFile:
    storage_key: str
    size_bytes: int


class ImportFileTooLargeError(ValueError):
    def __init__(self, *, max_size_bytes: int, actual_size_bytes: int) -> None:
        self.max_size_bytes = max_size_bytes
        self.actual_size_bytes = actual_size_bytes
        super().__init__(
            f"Import file exceeds maximum size of {max_size_bytes} bytes: "
            f"{actual_size_bytes} bytes received"
        )


class InvalidImportStorageKeyError(ValueError):
    pass


class LocalImportFileStorage:
    def __init__(self, root: Path, max_size_bytes: int) -> None:
        if max_size_bytes <= 0:
            raise ValueError("max_size_bytes must be greater than zero")

        self.root = root
        self._resolved_root = root.resolve(strict=False)
        self.max_size_bytes = max_size_bytes

    def save(self, stream: BinaryIO, *, user_id: int) -> StoredImportFile:
        if user_id <= 0:
            raise ValueError("user_id must be greater than zero")

        relative_path = Path("imports") / str(user_id) / f"{uuid4()}.csv"
        destination_path = self.root / relative_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)

        temp_path: Path | None = None
        size_bytes = 0

        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=destination_path.parent,
                prefix=f"{destination_path.stem}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temp_path = Path(temporary_file.name)

                while True:
                    chunk = stream.read(CHUNK_SIZE_BYTES)
                    if not chunk:
                        break

                    size_bytes += len(chunk)
                    if size_bytes > self.max_size_bytes:
                        raise ImportFileTooLargeError(
                            max_size_bytes=self.max_size_bytes,
                            actual_size_bytes=size_bytes,
                        )

                    temporary_file.write(chunk)

            os.replace(temp_path, destination_path)
        except Exception:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            raise

        return StoredImportFile(
            storage_key=relative_path.as_posix(),
            size_bytes=size_bytes,
        )

    def open_text(self, storage_key: str) -> TextIO:
        file_path = self._resolve_storage_key(storage_key)
        return file_path.open(mode="r", encoding="utf-8", newline="")

    def delete(self, storage_key: str) -> bool:
        file_path = self._resolve_storage_key(storage_key)
        if not file_path.exists():
            return False

        file_path.unlink()
        return True

    def _resolve_storage_key(self, storage_key: str) -> Path:
        relative_path = Path(storage_key)
        if relative_path.is_absolute():
            raise InvalidImportStorageKeyError("storage_key must be relative")
        if ".." in relative_path.parts:
            raise InvalidImportStorageKeyError(
                "storage_key must not contain parent-directory traversal"
            )

        resolved_path = (self.root / relative_path).resolve(strict=False)
        try:
            resolved_path.relative_to(self._resolved_root)
        except ValueError as exc:
            raise InvalidImportStorageKeyError(
                "storage_key must resolve within the storage root"
            ) from exc

        return resolved_path
