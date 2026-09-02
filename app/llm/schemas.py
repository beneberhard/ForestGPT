from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str
    stand_id: int | None = None
    simulation_run_id: int | None = None
    simulation_run_ids: list[int] = Field(default_factory=list)
    document_ids: list[int] = Field(default_factory=list, max_length=5)
    session_id: int | None = None
    top_k: int = Field(12, ge=1, le=50)


class ChatResponse(BaseModel):
    session_id: int
    answer: str
    retrieved_context: list[dict[str, Any]]
    simulation_summary: Any | None = None
