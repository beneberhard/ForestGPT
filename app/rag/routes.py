from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.geo.db import get_db
from app.geo.models import Document, DocumentChunk
from app.rag.index import embed_text, ingest_corpus
from app.rag.retrieve import retrieve_relevant_chunks
from app.rag.schemas import DocumentCreate, DocumentRead, RetrievalRequest, RetrievedChunk

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentRead)
def create_document(payload: DocumentCreate, db: Session = Depends(get_db)) -> Document:
    document = Document(
        title=payload.title,
        source_path=payload.source_path,
        metadata_json=payload.metadata_json,
    )
    db.add(document)
    db.flush()
    for chunk_text in payload.chunks:
        db.add(
            DocumentChunk(
                document_id=document.id,
                chunk_text=chunk_text,
                metadata_json=payload.metadata_json,
                embedding=embed_text(chunk_text),
            )
        )
    db.commit()
    db.refresh(document)
    return document


@router.get("", response_model=list[DocumentRead])
def list_documents(db: Session = Depends(get_db)) -> list[Document]:
    return db.query(Document).order_by(Document.created_at.desc()).all()


@router.post("/retrieve", response_model=list[RetrievedChunk])
def retrieve(payload: RetrievalRequest, db: Session = Depends(get_db)) -> list[RetrievedChunk]:
    return retrieve_relevant_chunks(db, payload.query, payload.top_k)


@router.post("/ingest-corpus")
def ingest_default_corpus(replace: bool = False, db: Session = Depends(get_db)) -> dict:
    return ingest_corpus(db, Path("data/RAG_text_corpus"), replace=replace)
