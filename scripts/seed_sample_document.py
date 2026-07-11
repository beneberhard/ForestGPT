from app.geo.db import SessionLocal
from app.geo.models import Document, DocumentChunk


SAMPLE_CHUNKS = [
    (
        "Thinning decisions should be matched to stand age, density, species ecology, "
        "site productivity, risk exposure, and the manager's target product mix."
    ),
    (
        "For Central European beech stands, moderate thinning can improve crown development "
        "and individual tree growth, but heavy interventions may increase drought and wind risk "
        "depending on site and stand structure."
    ),
    (
        "Growth model outputs should be interpreted as scenario evidence, not as automatic "
        "prescriptions. Local regulations, biodiversity objectives, regeneration status, and "
        "operational constraints remain important."
    ),
]


def main() -> None:
    db = SessionLocal()
    try:
        document = Document(
            title="Sample thinning guidance placeholder",
            source_path="seeded://sample-thinning-guidance",
            metadata_json={"species": "European beech", "region": "Central Europe", "topic": "thinning"},
        )
        db.add(document)
        db.flush()
        for chunk in SAMPLE_CHUNKS:
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_text=chunk,
                    metadata_json=document.metadata_json,
                )
            )
        db.commit()
        print(f"Seeded document {document.id}: {document.title}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
