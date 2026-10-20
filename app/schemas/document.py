from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    status: str
    progress: int
    page_count: int
    chunk_count: int
    error: str | None
    created_at: datetime


class CitationResponse(BaseModel):
    document_id: str
    document_name: str
    page_number: int
    chunk_id: str
    excerpt: str
    score: float
