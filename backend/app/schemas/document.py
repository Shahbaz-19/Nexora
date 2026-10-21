from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.document import DocumentStatus


class DocumentResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    original_filename: str
    file_type: str
    file_size: int
    status: DocumentStatus
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime
    chunk_count: int


class DocumentUploadResponse(DocumentResponse):
    pass
