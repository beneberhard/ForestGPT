import argparse
from pathlib import Path

from app.geo.db import SessionLocal
from app.rag.index import ingest_corpus


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest supported documents from data/RAG_text_corpus into the RAG index.")
    parser.add_argument("--replace", action="store_true", help="Delete and rebuild documents with matching source paths.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = ingest_corpus(db, Path("data/RAG_text_corpus"), replace=args.replace)
        print(result)
    finally:
        db.close()


if __name__ == "__main__":
    main()
