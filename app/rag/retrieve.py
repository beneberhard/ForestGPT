import re
from collections import Counter
from math import log

from sqlalchemy.orm import Session

from app.geo.models import DocumentChunk
from app.rag.index import cosine_similarity, embed_query
from app.rag.schemas import RetrievedChunk


TOKEN_RE = re.compile(r"[^\W\d_][^\W\d_-]{2,}", re.UNICODE)


def retrieve_relevant_chunks(db: Session, query: str, top_k: int = 5) -> list[RetrievedChunk]:
    query_terms = Counter(_tokenize(query))
    if not query_terms:
        return []

    chunks = db.query(DocumentChunk).limit(2000).all()
    if not chunks:
        return []

    bm25_scores = _bm25_scores(query_terms, chunks)
    query_embedding = embed_query(query)
    vector_scores = {
        chunk.id: cosine_similarity(query_embedding, chunk.embedding)
        for chunk in chunks
        if query_embedding is not None and chunk.embedding
    }
    bm25_norm = _normalize_scores(bm25_scores)
    vector_norm = _normalize_scores(vector_scores)

    scored: list[tuple[float, DocumentChunk]] = []
    for chunk in chunks:
        lexical = bm25_norm.get(chunk.id, 0.0)
        vector = vector_norm.get(chunk.id, 0.0)
        score = 0.55 * lexical + 0.45 * vector if vector_scores else lexical
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        RetrievedChunk(
            document_id=chunk.document_id,
            title=chunk.document.title,
            chunk_text=chunk.chunk_text,
            score=round(score, 4),
            metadata_json=chunk.metadata_json or chunk.document.metadata_json,
        )
        for score, chunk in scored[:top_k]
    ]


def _bm25_scores(query_terms: Counter, chunks: list[DocumentChunk]) -> dict[int, float]:
    k1 = 1.5
    b = 0.75
    tokenized = {chunk.id: _tokenize(chunk.chunk_text) for chunk in chunks}
    lengths = {chunk_id: len(tokens) for chunk_id, tokens in tokenized.items()}
    average_length = sum(lengths.values()) / max(len(lengths), 1)
    document_frequency = Counter()
    for tokens in tokenized.values():
        document_frequency.update(set(tokens))

    scores = {}
    document_count = len(chunks)
    for chunk in chunks:
        terms = Counter(tokenized[chunk.id])
        score = 0.0
        for term, query_count in query_terms.items():
            frequency = terms.get(term, 0)
            if frequency == 0:
                continue
            idf = log(1 + (document_count - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5))
            denominator = frequency + k1 * (1 - b + b * lengths[chunk.id] / max(average_length, 1))
            score += query_count * idf * (frequency * (k1 + 1)) / denominator
        if score > 0:
            scores[chunk.id] = score
    return scores


def _normalize_scores(scores: dict[int, float]) -> dict[int, float]:
    if not scores:
        return {}
    maximum = max(scores.values())
    if maximum <= 0:
        return {}
    return {key: value / maximum for key, value in scores.items()}


def _tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in TOKEN_RE.finditer(text)]
