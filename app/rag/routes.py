from pathlib import Path
from re import sub

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.geo.db import get_db
from app.geo.models import Document, DocumentChunk
from app.rag.index import bytes_sha256, document_with_hash_exists, embed_text, ingest_corpus, ingest_document_file, is_supported_document
from app.rag.retrieve import retrieve_relevant_chunks
from app.rag.schemas import DocumentCreate, DocumentRead, RetrievalRequest, RetrievedChunk

router = APIRouter(prefix="/documents", tags=["documents"])
CORPUS_DIR = Path("data/RAG_text_corpus")


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
    return ingest_corpus(db, CORPUS_DIR, replace=replace)


@router.post("/upload-ingest")
async def upload_and_ingest_document(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    original_name = file.filename or "uploaded_document"
    safe_name = safe_upload_name(original_name)
    target_path = CORPUS_DIR / safe_name
    if not is_supported_document(target_path):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Please upload PDF, DOCX, TXT, Markdown, CSV, XLSX, or XLSM.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    file_hash = bytes_sha256(content)
    if document_with_hash_exists(db, file_hash, current_embedding_only=True):
        return {
            "file_name": original_name,
            "saved_as": None,
            "documents_found": 1,
            "documents_ingested": 0,
            "documents_skipped": 1,
            "documents_skipped_existing_path": 0,
            "documents_skipped_existing_hash": 1,
            "chunks_created": 0,
            "embedding_enabled": True,
        }

    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    target_path = unique_upload_path(target_path, file_hash)
    target_path.write_bytes(content)

    result = ingest_document_file(db, target_path)
    return {"file_name": original_name, "saved_as": target_path.name, **result}


def safe_upload_name(file_name: str) -> str:
    path = Path(file_name)
    stem = sub(r"[^A-Za-z0-9._-]+", "_", path.stem).strip("._-") or "uploaded_document"
    suffix = sub(r"[^A-Za-z0-9.]+", "", path.suffix.lower())
    return f"{stem}{suffix}"


def unique_upload_path(path: Path, file_hash: str) -> Path:
    if not path.exists():
        return path
    candidate = path.with_name(f"{path.stem}_{file_hash[:10]}{path.suffix}")
    counter = 2
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}_{file_hash[:10]}_{counter}{path.suffix}")
        counter += 1
    return candidate
