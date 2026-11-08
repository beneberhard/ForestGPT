import os
from dotenv import load_dotenv
from pathlib import Path

# Explicit process/container settings take precedence over local .env defaults.
load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://forestgpt_user:forestgpt_password@localhost:5433/forestgpt",
)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "lm-studio")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:1234/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "local-model")
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "1024"))
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "openai")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY") or OPENAI_API_KEY
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "https://api.openai.com/v1")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
OCR_LANGUAGES = os.getenv("OCR_LANGUAGES", "eng+deu+ita")
OCR_DPI = int(os.getenv("OCR_DPI", "250"))
OCR_MIN_TEXT_CHARACTERS = int(os.getenv("OCR_MIN_TEXT_CHARACTERS", "40"))
SIMULATION_ADAPTER = os.getenv("SIMULATION_ADAPTER", "r3pg")
R3PG_RUNNER_PATH = Path(os.getenv("R3PG_RUNNER_PATH", "scripts/r3pg_runner.R"))
R3PG_TABLE_BUILDER_PATH = Path(os.getenv("R3PG_TABLE_BUILDER_PATH", "scripts/r3pg_table_builder.R"))
RSCRIPT_BIN = os.getenv("RSCRIPT_BIN", "Rscript")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY is missing. Please add it to your .env file")

DATA_DIR = Path("data")
STORAGE_DIR = Path("storage")
