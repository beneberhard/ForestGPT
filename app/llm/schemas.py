from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str
    stand_id: int | None = None
    simulation_run_id: int | None = None
    session_id: int | None = None
    top_k: int = Field(5, ge=1, le=20) #greater than or equal, less than or equal; top_k must be between 1 and 20


class ChatResponse(BaseModel):
    session_id: int
    answer: str
    retrieved_context: list[dict[str, Any]]
    simulation_summary: dict[str, Any] | None = None
