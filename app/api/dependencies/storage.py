from app.core.config import get_settings
from app.storage import LocalImportFileStorage


def get_import_file_storage() -> LocalImportFileStorage:
    settings = get_settings()
    return LocalImportFileStorage(
        root=settings.upload_dir,
        max_size_bytes=settings.max_upload_size_mb * 1024 * 1024,
    )
