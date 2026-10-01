# ForestGPT

ForestGPT is a research prototype for stand-level forest management support. It combines:

- a conversational interface;
- retrieval-augmented generation (RAG) from forestry documents;
- forest growth simulations with `r3PG`; and
- geospatial stand data stored in PostGIS.

The application brings stand information, simulation results, spatial context, field observations, and retrieved literature together in one response. The backend controls this workflow. The language model receives the assembled context and communicates the result; it does not autonomously choose or run tools.

## Main features

- Create and manage forest stands and stand geometries.
- Display stands on an interactive Leaflet map.
- Calculate terrain and accessibility information from spatial data.
- Record stand-level field observations.
- Prepare missing simulation inputs with a yield-table-based default-value engine.
- Run and compare `r3PG` growth and thinning scenarios.
- Upload and ingest PDF, DOCX, TXT, Markdown, CSV, XLSX, and XLSM documents.
- Apply OCR to scanned PDFs and PDFs created from images.
- Retrieve relevant passages using hybrid lexical and vector search.
- Generate source-referenced answers using an OpenAI-compatible language model.

## Architecture

ForestGPT runs as two Docker services:

- `db`: PostgreSQL with PostGIS;
- `app`: FastAPI backend, Leaflet frontend, RAG pipeline, and the Python-to-R simulation bridge.

The principal components are located in:

```text
app/
  api/          FastAPI application
  geo/          stand records and PostGIS access
  spatial/      terrain and road analysis
  simulation/   r3PG integration and default-value engine
  rag/          document ingestion, indexing, and retrieval
  llm/          prompt construction and response generation
frontend/       Leaflet web interface
scripts/        database, ingestion, and r3PG utilities
```

## Requirements

- Docker Desktop with Docker Compose
- an OpenAI API key or another OpenAI-compatible language-model endpoint
- an embedding endpoint compatible with the OpenAI embeddings API

Docker installs the required Python packages, R, `r3PG`, PostGIS, and English, German, and Italian Tesseract OCR data.

## Quick start

1. Clone the repository and enter its directory:

```bash
git clone <repository-url>
cd ForestGPT
```

2. Create a `.env` file. For the OpenAI API, a minimal configuration is:

```dotenv
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1-mini

EMBEDDING_PROVIDER=openai
EMBEDDING_API_KEY=your-api-key
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
```

Do not commit the `.env` file or any API key.

3. Build and start the application:

```bash
docker compose up -d --build
```

The startup script waits for PostGIS, creates the required database tables, and starts the application.

4. Open ForestGPT:

```text
http://127.0.0.1:8005/app/
```

API documentation is available at:

```text
http://127.0.0.1:8005/docs
```

To stop the application:

```bash
docker compose down
```

## Knowledge-base ingestion

Documents can be uploaded from the **Knowledge base** panel in the web interface.

Files placed manually in `data/RAG_text_corpus` can be ingested with:

```bash
docker compose exec app python -m scripts.ingest_rag_corpus
```

Ingestion is incremental. Existing documents are identified by their source path and file hash. To deliberately rebuild matching documents, run:

```bash
docker compose exec app python -m scripts.ingest_rag_corpus --replace
```

OCR behavior can be configured with `OCR_LANGUAGES`, `OCR_DPI`, and `OCR_MIN_TEXT_CHARACTERS`.

## PostGIS and QGIS

The default host connection for QGIS or another database client is:

```text
Host: localhost
Port: 5433
Database: forestgpt
Username: forestgpt_user
Password: forestgpt_password
```

These development credentials can be changed in `docker-compose.yml` before deployment.

## Configuration

Important environment variables include:

| Variable | Purpose | Default |
|---|---|---|
| `APP_HOST_PORT` | Web application port on the host | `8005` |
| `POSTGRES_HOST_PORT` | PostgreSQL port on the host | `5433` |
| `OPENAI_BASE_URL` | OpenAI-compatible chat endpoint | `http://host.docker.internal:1234/v1` |
| `OPENAI_MODEL` | Conversational model | `local-model` |
| `EMBEDDING_BASE_URL` | Embedding API endpoint | `https://api.openai.com/v1` |
| `EMBEDDING_MODEL` | Embedding model | `text-embedding-3-small` |
| `SIMULATION_ADAPTER` | Growth simulator | `r3pg` |
| `OCR_LANGUAGES` | Tesseract OCR languages | `eng+deu+ita` |

## Development status

ForestGPT is an experimental research prototype. Simulation results depend on model assumptions, parameter sets, climate inputs, stand data, and regional calibration. Generated answers may contain errors or omit relevant considerations.

The application is intended to support professional deliberation, not to replace the judgment of qualified forest managers. Validate inputs, simulations, retrieved evidence, and recommendations before using them in operational decisions.

The current Docker and database configuration is intended for local development and evaluation. Additional authentication, authorization, secret management, network security, backups, and deployment hardening are required before public or production use.

## Contact

Benno Richard Eberhard  
Institute of BioEconomy (IBE), National Research Council of Italy (CNR)  
`bennorichardeberhard@cnr.it`
