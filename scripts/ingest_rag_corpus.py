import argparse
import logging
from pathlib import Path

from app.geo.db import SessionLocal
from app.rag.index import ingest_corpus, repair_document_embeddings


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Ingest supported documents from data/RAG_text_corpus into the RAG index.")
    parser.add_argument("--replace", action="store_true", help="Rebuild chunks and embeddings for matching source paths.")
    parser.add_argument("--embeddings-only", action="store_true", help="Repair existing vectors, preserving document text and IDs.")
    parser.add_argument("--prune-missing", action="store_true", help="Remove indexed files missing from the corpus folder after successful ingestion.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.embeddings_only:
            result = repair_document_embeddings(db)
        else:
            result = ingest_corpus(db, Path("data/RAG_text_corpus"), replace=args.replace, prune_missing=args.prune_missing)
        print(result)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
