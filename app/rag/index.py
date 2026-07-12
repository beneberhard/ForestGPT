from __future__ import annotations

import csv
import math
from hashlib import sha256
from functools import lru_cache
from pathlib import Path
from typing import BinaryIO

from docx import Document as DocxDocument
from openai import OpenAI
from openpyxl import load_workbook
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.config import EMBEDDING_API_KEY, EMBEDDING_BASE_URL, EMBEDDING_MODEL, EMBEDDING_PROVIDER
from app.geo.models import Document, DocumentChunk


CHUNK_SIZE = 1200
CHUNK_OVERLAP = 180
SUPPORTED_DOCUMENT_SUFFIXES = {".pdf", ".txt", ".md", ".docx", ".csv", ".xlsx", ".xlsm"}


def ingest_corpus(db: Session, corpus_dir: Path, replace: bool = False) -> dict:
    if not corpus_dir.exists():
        return {
            "documents_found": 0,
            "documents_ingested": 0,
            "documents_skipped": 0,
            "documents_skipped_existing_path": 0,
            "documents_skipped_existing_hash": 0,
            "chunks_created": 0,
            "embedding_enabled": True,
        }

    document_paths = sorted(path for path in corpus_dir.iterdir() if path.is_file() and is_supported_document(path))
    ingested = 0
    chunks_created = 0
    skipped = 0
    skipped_existing_path = 0
    skipped_existing_hash = 0
    embedding_enabled = True

    for path in document_paths:
        result = ingest_document_file(db, path, replace=replace, commit=False)
        ingested += int(result["documents_ingested"])
        chunks_created += int(result["chunks_created"])
        skipped += int(result["documents_skipped"])
        skipped_existing_path += int(result["documents_skipped_existing_path"])
        skipped_existing_hash += int(result["documents_skipped_existing_hash"])
        embedding_enabled = embedding_enabled and bool(result["embedding_enabled"])

    db.commit()
    return {
        "documents_found": len(document_paths),
        "documents_ingested": ingested,
        "documents_skipped": skipped,
        "documents_skipped_existing_path": skipped_existing_path,
        "documents_skipped_existing_hash": skipped_existing_hash,
        "chunks_created": chunks_created,
        "embedding_enabled": embedding_enabled,
    }


def ingest_document_file(db: Session, path: Path, replace: bool = False, commit: bool = True) -> dict:
    if not is_supported_document(path):
        raise ValueError(f"Unsupported document type: {path.suffix or 'unknown'}")

    source_path = path.as_posix()
    file_hash = file_sha256(path)
    existing = db.query(Document).filter(Document.source_path == source_path).first()
    if existing and not replace and document_has_current_embedding(existing):
        return _ingest_result(skipped=1, skipped_existing_path=1)
    if existing:
        db.delete(existing)
        db.flush()
    elif not replace and document_with_hash_exists(db, file_hash, current_embedding_only=True):
        return _ingest_result(skipped=1, skipped_existing_hash=1)

    text = extract_document_text(path)
    chunks = chunk_text(text)
    document = Document(
        title=path.stem,
        source_path=source_path,
        metadata_json={
            "source_type": path.suffix.lower().lstrip("."),
            "sha256": file_hash,
            "file_name": path.name,
            **embedding_metadata(),
        },
    )
    db.add(document)
    db.flush()

    embedding_enabled = True
    chunks_created = 0
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

    if commit:
        db.commit()

    return _ingest_result(ingested=1, chunks_created=chunks_created, embedding_enabled=embedding_enabled)


def _ingest_result(
    ingested: int = 0,
    skipped: int = 0,
    skipped_existing_path: int = 0,
    skipped_existing_hash: int = 0,
    chunks_created: int = 0,
    embedding_enabled: bool = True,
) -> dict:
    return {
        "documents_found": 1,
        "documents_ingested": ingested,
        "documents_skipped": skipped,
        "documents_skipped_existing_path": skipped_existing_path,
        "documents_skipped_existing_hash": skipped_existing_hash,
        "chunks_created": chunks_created,
        "embedding_enabled": embedding_enabled,
    }


def is_supported_document(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_DOCUMENT_SUFFIXES


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as file:
        update_hash(digest, file)
    return digest.hexdigest()


def bytes_sha256(content: bytes) -> str:
    digest = sha256()
    digest.update(content)
    return digest.hexdigest()


def update_hash(digest, file: BinaryIO) -> None:
    for block in iter(lambda: file.read(1024 * 1024), b""):
        digest.update(block)


def embedding_metadata() -> dict[str, str]:
    return {
        "embedding_provider": EMBEDDING_PROVIDER,
        "embedding_model": EMBEDDING_MODEL,
    }


def document_has_current_embedding(document: Document) -> bool:
    metadata = document.metadata_json or {}
    expected = embedding_metadata()
    return all(metadata.get(key) == value for key, value in expected.items())


def document_with_hash_exists(db: Session, file_hash: str, current_embedding_only: bool = False) -> bool:
    documents = db.query(Document.metadata_json).filter(Document.metadata_json.isnot(None)).all()
    for (metadata,) in documents:
        metadata = metadata or {}
        if metadata.get("sha256") != file_hash:
            continue
        if current_embedding_only and any(metadata.get(key) != value for key, value in embedding_metadata().items()):
            continue
        return True
    return False


def extract_document_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf_text(path)
    if suffix in {".txt", ".md"}:
        return extract_text_file(path)
    if suffix == ".docx":
        return extract_docx_text(path)
    if suffix == ".csv":
        return extract_csv_text(path)
    if suffix in {".xlsx", ".xlsm"}:
        return extract_excel_text(path)
    raise ValueError(f"Unsupported document type: {suffix or 'unknown'}")


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            pages.append(text)
    return "\n\n".join(pages)


def extract_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def extract_docx_text(path: Path) -> str:
    document = DocxDocument(str(path))
    sections = []
    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    if paragraphs:
        sections.append("\n".join(paragraphs))

    table_sections = []
    for table_index, table in enumerate(document.tables, start=1):
        rows = []
        for row in table.rows:
            cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
            if any(cells):
                rows.append("\t".join(cells))
        if rows:
            table_sections.append(f"Table {table_index}\n" + "\n".join(rows))
    if table_sections:
        sections.append("\n\n".join(table_sections))

    return "\n\n".join(sections)


def extract_csv_text(path: Path) -> str:
    content = path.read_text(encoding="utf-8-sig", errors="replace")
    rows = csv.reader(content.splitlines())
    return "\n".join("\t".join(cell.strip() for cell in row) for row in rows)


def extract_excel_text(path: Path) -> str:
    workbook = load_workbook(path, read_only=True, data_only=True)
    sections = []
    try:
        for sheet in workbook.worksheets:
            rows = []
            for row in sheet.iter_rows(values_only=True):
                values = ["" if value is None else str(value).strip() for value in row]
                if any(values):
                    rows.append("\t".join(values))
            if rows:
                sections.append(f"Sheet: {sheet.title}\n" + "\n".join(rows))
    finally:
        workbook.close()
    return "\n\n".join(sections)


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
    return _embed(text)


def embed_query(text: str) -> list[float] | None:
    return _embed(text)


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
def _embedding_client() -> OpenAI | None:
    if EMBEDDING_PROVIDER.lower() != "openai":
        return None
    if not EMBEDDING_API_KEY:
        return None
    return OpenAI(api_key=EMBEDDING_API_KEY, base_url=EMBEDDING_BASE_URL)


def _embed(text: str) -> list[float] | None:
    client = _embedding_client()
    if client is None:
        return None
    try:
        response = client.embeddings.create(model=EMBEDDING_MODEL, input=text)
        return [float(value) for value in response.data[0].embedding]
    except Exception:
        return None
