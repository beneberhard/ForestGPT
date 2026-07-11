from __future__ import annotations

import math
from hashlib import sha256
from functools import lru_cache
from pathlib import Path

from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.config import EMBEDDING_MODEL, MODEL_CACHE_DIR
from app.geo.models import Document, DocumentChunk


CHUNK_SIZE = 1200
CHUNK_OVERLAP = 180


def ingest_corpus(db: Session, corpus_dir: Path, replace: bool = False) -> dict:
    pdf_paths = sorted(corpus_dir.glob("*.pdf"))
    ingested = 0
    chunks_created = 0
    skipped = 0
    skipped_existing_path = 0
    skipped_existing_hash = 0
    embedding_enabled = True

    for path in pdf_paths:
        source_path = path.as_posix()
        file_hash = file_sha256(path)
        existing = db.query(Document).filter(Document.source_path == source_path).first()
        if existing and not replace:
            skipped += 1
            skipped_existing_path += 1
            continue
        if existing and replace:
            db.delete(existing)
            db.flush()
        elif not replace and document_with_hash_exists(db, file_hash):
            skipped += 1
            skipped_existing_hash += 1
            continue

        text = extract_pdf_text(path)
        chunks = chunk_text(text)
        document = Document(
            title=path.stem,
            source_path=source_path,
            metadata_json={
                "source_type": "pdf",
                "sha256": file_hash,
                "file_name": path.name,
            },
        )
        db.add(document)
        db.flush()

        for chunk in chunks:
            embedding = embed_text(chunk)
            if embedding is None:
                embedding_enabled = False
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_text=chunk,
                    metadata_json=None,
                    embedding=embedding,
                )
            )
            chunks_created += 1
        ingested += 1

    db.commit()
    return {
        "documents_found": len(pdf_paths),
        "documents_ingested": ingested,
        "documents_skipped": skipped,
        "documents_skipped_existing_path": skipped_existing_path,
        "documents_skipped_existing_hash": skipped_existing_hash,
        "chunks_created": chunks_created,
        "embedding_enabled": embedding_enabled,
    }


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def document_with_hash_exists(db: Session, file_hash: str) -> bool:
    documents = db.query(Document.metadata_json).filter(Document.metadata_json.isnot(None)).all()
    return any((metadata or {}).get("sha256") == file_hash for (metadata,) in documents)


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            pages.append(text)
    return "\n\n".join(pages)


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = max(end - overlap, start + 1)
    return chunks


def embed_text(text: str) -> list[float] | None:
    model = _embedding_model()
    if model is None:
        return None
    try:
        return [float(value) for value in model.get_text_embedding(text)]
    except Exception:
        return None


def embed_query(text: str) -> list[float] | None:
    model = _embedding_model()
    if model is None:
        return None
    try:
        return [float(value) for value in model.get_query_embedding(text)]
    except Exception:
        return None


def cosine_similarity(left: list[float] | None, right: list[float] | None) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


@lru_cache(maxsize=1)
def _embedding_model():
    try:
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding

        MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        return HuggingFaceEmbedding(model_name=EMBEDDING_MODEL, cache_folder=str(MODEL_CACHE_DIR))
    except Exception:
        return None
