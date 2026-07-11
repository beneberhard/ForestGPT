#!/bin/sh
set -eu

echo "Waiting for database..."
python - <<'PY'
import time

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.geo.db import engine

for attempt in range(60):
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        break
    except OperationalError:
        if attempt == 59:
            raise
        time.sleep(1)
PY

echo "Preparing database schema..."
python -m scripts.create_tables

echo "Starting ForestGPT..."
exec uvicorn app.api.main:app --host 0.0.0.0 --port "${APP_PORT:-8005}"
