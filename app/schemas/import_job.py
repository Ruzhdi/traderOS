from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.import_job import ImportJobStatus


class ImportJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: ImportJobStatus
    original_filename: str
    total_rows: int | None
    imported_rows: int
    rejected_rows: int
    failure_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
