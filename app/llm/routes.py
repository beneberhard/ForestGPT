from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.geo.db import get_db
from app.llm.schemas import ChatRequest, ChatResponse
from app.llm.service import answer_manager_question

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    try:
        return answer_manager_question(db, payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
