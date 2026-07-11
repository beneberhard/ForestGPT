from sqlalchemy import text

from app.geo.db import Base, engine
from app.geo import models  # noqa: F401


def main() -> None:
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.create_all(bind=engine)
    _apply_dev_schema_updates()
    print("Database tables are ready.")


def _apply_dev_schema_updates() -> None:
    statements = [
        "ALTER TABLE stands ADD COLUMN IF NOT EXISTS name VARCHAR(255)",
        "ALTER TABLE stands ADD COLUMN IF NOT EXISTS species VARCHAR(100)",
        "ALTER TABLE stands ADD COLUMN IF NOT EXISTS area_ha DOUBLE PRECISION",
        "ALTER TABLE stands ADD COLUMN IF NOT EXISTS age_years INTEGER",
        "ALTER TABLE stands ADD COLUMN IF NOT EXISTS geometry geometry(POLYGON, 4326)",
        "ALTER TABLE stands ADD COLUMN IF NOT EXISTS properties JSON",
        "ALTER TABLE stands ADD COLUMN IF NOT EXISTS created_at TIMESTAMP",
        "ALTER TABLE stand_observations ADD COLUMN IF NOT EXISTS stand_id INTEGER REFERENCES stands(id)",
        "ALTER TABLE stand_observations ADD COLUMN IF NOT EXISTS observed_at TIMESTAMP",
        "ALTER TABLE stand_observations ADD COLUMN IF NOT EXISTS observer VARCHAR(255)",
        "ALTER TABLE stand_observations ADD COLUMN IF NOT EXISTS category VARCHAR(100)",
        "ALTER TABLE stand_observations ADD COLUMN IF NOT EXISTS note TEXT",
        "ALTER TABLE stand_observations ADD COLUMN IF NOT EXISTS properties JSON",
        "ALTER TABLE stand_observations ADD COLUMN IF NOT EXISTS created_at TIMESTAMP",
        "ALTER TABLE simulation_runs ADD COLUMN IF NOT EXISTS stand_id INTEGER REFERENCES stands(id)",
        "ALTER TABLE simulation_runs ALTER COLUMN stand_id DROP NOT NULL",
        "ALTER TABLE simulation_runs ADD COLUMN IF NOT EXISTS model_name VARCHAR(100)",
        "ALTER TABLE simulation_runs ADD COLUMN IF NOT EXISTS model_version VARCHAR(100)",
        "ALTER TABLE simulation_runs ADD COLUMN IF NOT EXISTS input_parameters JSON",
        "ALTER TABLE simulation_runs ADD COLUMN IF NOT EXISTS summary JSON",
        "ALTER TABLE simulation_runs ADD COLUMN IF NOT EXISTS status VARCHAR(50)",
        "ALTER TABLE simulation_runs ADD COLUMN IF NOT EXISTS error_message TEXT",
        "ALTER TABLE simulation_runs ADD COLUMN IF NOT EXISTS created_at TIMESTAMP",
        "ALTER TABLE simulation_runs ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP",
        "ALTER TABLE simulation_outputs ADD COLUMN IF NOT EXISTS run_id INTEGER REFERENCES simulation_runs(id)",
        "ALTER TABLE simulation_outputs ADD COLUMN IF NOT EXISTS year INTEGER",
        "ALTER TABLE simulation_outputs ADD COLUMN IF NOT EXISTS output JSON",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS title VARCHAR(500)",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_path VARCHAR(1000)",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS metadata_json JSON",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS created_at TIMESTAMP",
        "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS document_id INTEGER REFERENCES documents(id)",
        "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS chunk_text TEXT",
        "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS metadata_json JSON",
        "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS embedding JSON",
        "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS stand_id INTEGER REFERENCES stands(id)",
        "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS title VARCHAR(255)",
        "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS created_at TIMESTAMP",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS session_id INTEGER REFERENCES chat_sessions(id)",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS role VARCHAR(50)",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS content TEXT",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS metadata_json JSON",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS created_at TIMESTAMP",
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


if __name__ == "__main__":
    main()
