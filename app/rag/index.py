from __future__ import annotations

import csv
import math
import logging
from hashlib import sha256
from functools import lru_cache
from pathlib import Path
from typing import BinaryIO

import pymupdf
import pytesseract
import tiktoken
from docx import Document as DocxDocument
from openai import OpenAI
from openpyxl import load_workbook
from PIL import Image
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.config import (
    EMBEDDING_API_KEY,
    EMBEDDING_BASE_URL,
    EMBEDDING_MODEL,
    EMBEDDING_PROVIDER,
    OCR_DPI,
    OCR_LANGUAGES,
    OCR_MIN_TEXT_CHARACTERS,
)
from app.geo.models import Document, DocumentChunk


CHUNK_SIZE = 600
CHUNK_OVERLAP = 90
CHUNK_TOKENIZER = "cl100k_base"
EMBEDDING_BATCH_SIZE = 64
SUPPORTED_DOCUMENT_SUFFIXES = {".pdf", ".txt", ".md", ".docx", ".csv", ".xlsx", ".xlsm"}
logger = logging.getLogger(__name__)


def ingest_corpus(db: Session, corpus_dir: Path, replace: bool = False, prune_missing: bool = False) -> dict:
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

    removed = 0
    if prune_missing:
        current_paths = {path.resolve() for path in document_paths}
        for document in db.query(Document).all():
            if not document.source_path:
                continue
            source = Path(document.source_path)
            if source.parent.resolve() == corpus_dir.resolve() and source.resolve() not in current_paths:
                db.delete(document)
                removed += 1
    db.commit()
    return {
        "documents_found": len(document_paths),
        "documents_ingested": ingested,
        "documents_skipped": skipped,
        "documents_skipped_existing_path": skipped_existing_path,
        "documents_skipped_existing_hash": skipped_existing_hash,
        "chunks_created": chunks_created,
        "embedding_enabled": embedding_enabled,
        "documents_removed": removed,
    }


def ingest_document_file(db: Session, path: Path, replace: bool = False, commit: bool = True) -> dict:
    if not is_supported_document(path):
        raise ValueError(f"Unsupported document type: {path.suffix or 'unknown'}")

    source_path = path.as_posix()
    file_hash = file_sha256(path)
    existing = db.query(Document).filter(Document.source_path == source_path).first()
    if (
        existing and not replace and document_has_current_embedding(existing)
        and document_has_current_chunking(existing)
        and (existing.metadata_json or {}).get("sha256") == file_hash
    ):
        return _ingest_result(skipped=1, skipped_existing_path=1)
    if not existing and not replace and document_with_hash_exists(db, file_hash, current_embedding_only=True):
        return _ingest_result(skipped=1, skipped_existing_hash=1)

    text = extract_document_text(path)
    chunks = chunk_text(text)
    if not chunks:
        raise ValueError(f"No readable text found in {path.name}")
    # Finish API work before replacing any existing chunks. A failed corpus run
    # is rolled back by the caller, leaving the previous index available.
    embeddings = []
    for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
        embeddings.extend(embed_texts(chunks[start:start + EMBEDDING_BATCH_SIZE]))
    document = existing or Document(title=path.stem, source_path=source_path)
    if existing:
        document.chunks.clear()
    document.title = path.stem
    document.metadata_json = {
        "source_type": path.suffix.lower().lstrip("."),
        "sha256": file_hash,
        "file_name": path.name,
        **embedding_metadata(),
        **chunking_metadata(),
    }
    db.add(document)
    db.flush()

    embedding_enabled = True
    chunks_created = 0
    for chunk, embedding in zip(chunks, embeddings):
        db.add(
            DocumentChunk(
                document_id=document.id,
                chunk_text=chunk,
                metadata_json={"token_count": len(_chunk_tokenizer().encode_ordinary(chunk))},
                embedding=embedding,
            )
        )
        chunks_created += 1

    if commit:
        db.commit()

    logger.info("Ingested %s: %s chunks with embeddings", path.name, chunks_created)

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
    return (
        all(metadata.get(key) == value for key, value in expected.items())
        and bool(document.chunks)
        and all(bool(chunk.embedding) for chunk in document.chunks)
    )


def chunking_metadata() -> dict:
    return {"chunk_tokenizer": CHUNK_TOKENIZER, "chunk_size_tokens": CHUNK_SIZE, "chunk_overlap_tokens": CHUNK_OVERLAP}


def document_has_current_chunking(document: Document) -> bool:
    metadata = document.metadata_json or {}
    return all(metadata.get(key) == value for key, value in chunking_metadata().items())


def document_with_hash_exists(db: Session, file_hash: str, current_embedding_only: bool = False) -> bool:
    documents = db.query(Document).filter(Document.metadata_json.isnot(None)).all()
    for document in documents:
        metadata = document.metadata_json or {}
        if metadata.get("sha256") != file_hash:
            continue
        if current_embedding_only and not (
            document_has_current_embedding(document) and document_has_current_chunking(document)
        ):
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
    rendered_pdf = None
    try:
        for page_number, page in enumerate(reader.pages):
            native_text = page.extract_text() or ""
            if has_meaningful_text(native_text):
                pages.append(native_text.strip())
                continue

            if rendered_pdf is None:
                rendered_pdf = pymupdf.open(path)
            ocr_text = extract_pdf_page_with_ocr(rendered_pdf, page_number)
            text = ocr_text if has_meaningful_text(ocr_text) else native_text
            if text.strip():
                pages.append(text.strip())
    finally:
        if rendered_pdf is not None:
            rendered_pdf.close()

    if not pages:
        raise ValueError(
            "No readable text was found in the PDF. The file may be blank, "
            "damaged, or use an OCR language that is not configured."
        )
    return "\n\n".join(pages)


def has_meaningful_text(text: str) -> bool:
    return sum(character.isalnum() for character in text) >= OCR_MIN_TEXT_CHARACTERS


def extract_pdf_page_with_ocr(document: pymupdf.Document, page_number: int) -> str:
    page = document.load_page(page_number)
    scale = OCR_DPI / 72
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    try:
        return pytesseract.image_to_string(image, lang=OCR_LANGUAGES)
    except pytesseract.TesseractNotFoundError as exc:
        raise ValueError(
            "This PDF contains image-only pages, but the OCR engine is not installed."
        ) from exc
    except pytesseract.TesseractError as exc:
        raise ValueError(
            f"OCR failed for PDF page {page_number + 1}: {exc}"
        ) from exc


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


@lru_cache(maxsize=1)
def _chunk_tokenizer():
    return tiktoken.get_encoding(CHUNK_TOKENIZER)


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Token windows with up to `overlap` shared tokens, preserving Unicode.

    Boundaries can move inward by a few tokens to avoid splitting a UTF-8
    character. Ordinary text, including literal special-token strings, is safe.
    """
    if chunk_size <= 0 or not 0 <= overlap < chunk_size:
        raise ValueError("Require chunk_size > 0 and 0 <= overlap < chunk_size")
    if not text.strip():
        return []
    encoding = _chunk_tokenizer()
    tokens = encoding.encode_ordinary(text)

    def safe_boundary(position: int) -> bool:
        return position in (0, len(tokens)) or encoding.decode_single_token_bytes(tokens[position])[0] & 0xC0 != 0x80

    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        while end > start:
            if safe_boundary(end):
                chunk = encoding.decode(tokens[start:end], errors="strict")
                if len(encoding.encode_ordinary(chunk)) <= chunk_size:
                    break
            end -= 1
        if end == start:
            raise ValueError("chunk_size is too small to preserve a Unicode character")
        chunks.append(chunk)
        if end == len(tokens):
            break
        next_start = max(end - overlap, start + 1)
        while not safe_boundary(next_start):
            next_start += 1
        start = min(next_start, end)
    return chunks


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch, rejecting partial responses instead of storing null vectors."""
    if not texts:
        return []
    client = _embedding_client()
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    vectors = sorted(response.data, key=lambda item: item.index)
    if [item.index for item in vectors] != list(range(len(texts))) or any(not item.embedding for item in vectors):
        raise ValueError("Embedding API returned an incomplete batch")
    return [[float(value) for value in item.embedding] for item in vectors]


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
        raise ValueError(f"Unsupported EMBEDDING_PROVIDER: {EMBEDDING_PROVIDER!r}; expected 'openai'.")
    if not EMBEDDING_API_KEY:
        raise ValueError("An embedding API key is required.")
    return OpenAI(api_key=EMBEDDING_API_KEY, base_url=EMBEDDING_BASE_URL)


def _embed(text: str) -> list[float] | None:
    client = _embedding_client()
    if client is None:
        return None
    try:
        response = client.embeddings.create(model=EMBEDDING_MODEL, input=text)
        return [float(value) for value in response.data[0].embedding]
    except Exception as exc:
        logger.warning("Embedding generation failed (%s); using lexical retrieval only.", type(exc).__name__)
        return None


def repair_document_embeddings(db: Session, batch_size: int = 16) -> dict:
    """Generate missing or outdated vectors without changing document text or IDs."""
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    client = _embedding_client()
    updated_documents = 0
    updated_chunks = 0
    for document in db.query(Document).order_by(Document.id).all():
        if document_has_current_embedding(document) or not document.chunks:
            continue
        chunks = sorted(document.chunks, key=lambda chunk: chunk.id)
        try:
            for start in range(0, len(chunks), batch_size):
                batch = chunks[start:start + batch_size]
                response = client.embeddings.create(
                    model=EMBEDDING_MODEL, input=[chunk.chunk_text for chunk in batch],
                )
                vectors = sorted(response.data, key=lambda item: item.index)
                if [item.index for item in vectors] != list(range(len(batch))) or any(not item.embedding for item in vectors):
                    raise ValueError("Embedding API returned an incomplete batch")
                for chunk, item in zip(batch, vectors):
                    chunk.embedding = [float(value) for value in item.embedding]
            document.metadata_json = {**(document.metadata_json or {}), **embedding_metadata()}
            db.commit()
        except Exception:
            db.rollback()
            raise
        updated_documents += 1
        updated_chunks += len(chunks)
        logger.info("Updated embeddings for document %s (%s chunks)", document.id, len(chunks))
    return {"documents_updated": updated_documents, "chunks_updated": updated_chunks}
