from typing import Any

from pydantic import BaseModel, Field


class DocumentCreate(BaseModel):
    title: str
    source_path: str | None = None
    metadata_json: dict[str, Any] | None = None
    chunks: list[str] = Field(default_factory=list)


class DocumentRead(BaseModel):
    id: int
    title: str
    source_path: str | None = None
    metadata_json: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class RetrievedChunk(BaseModel):
    document_id: int
    title: str
    chunk_text: str
    score: float
    metadata_json: dict[str, Any] | None = None


class RetrievalRequest(BaseModel):
    query: str
    top_k: int = Field(5, ge=1, le=20)
