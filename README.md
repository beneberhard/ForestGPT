# ForestGPT Docker Start

ForestGPT now runs as two Docker services:

- `db`: PostGIS/PostgreSQL
- `app`: FastAPI API plus the Leaflet frontend

Start everything from the project folder:

```bash
docker compose up -d --build (only after Docker-related changes)
docker compose up -d
```

Then open:

```text
http://127.0.0.1:8005/app/
```

API docs are available at:

```text
http://127.0.0.1:8005/docs
```

For QGIS, connect to the database with:

```text
Host: localhost
Port: 5433
Database: forestgpt
Username: forestgpt_user
Password: forestgpt_password
```

Useful commands:

```bash
docker compose logs -f app
docker compose down
```

RAG ingestion is incremental by default. The Leaflet app can upload and ingest PDF, DOCX, TXT, Markdown, CSV, XLSX, and XLSM files from the **Knowledge base** panel. When you add documents manually to `data/RAG_text_corpus`, run:

```bash
docker compose exec app python -m scripts.ingest_rag_corpus
```
Existing documents are skipped by stored source path and file hash. Use

```bash
docker compose exec app python -m scripts.ingest_rag_corpus --replace
``` 
only when you deliberately want to rebuild matching documents.

Embeddings use OpenAI-compatible embeddings by default:

```text
EMBEDDING_PROVIDER=openai
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
```

The app records the embedding provider and model with each ingested document. If the embedding model changes, existing corpus files are re-embedded the next time ingestion is run.

The Docker image does not install Streamlit. The old `streamlit_app.py` dashboard is kept only as an optional local development helper. To use it locally, install:

```bash
pip install -r requirements-dev.txt
```


The local `.env` file is not copied into the Docker image. Docker Compose only passes needed environment values to the running container.

---


From the project folder, you can open the PostGIS database with:

```bash
docker compose exec db psql -U forestgpt_user -d forestgpt
```

Then run the update inside psql:
sql
UPDATE stands
SET age_years = 80
WHERE id = 41;

Check it worked:
sql
SELECT id, name, species, age_years
FROM stands
WHERE id = 41;

Exit psql with:
 \q





The Python Interpreter is forestgpt_trial

In case of loading (API, Streamlit) difficulties due to a port mismatch (FastAPI starts on 8002, Streamlit calls 8003) do the following:
First stop old processes:
pkill -f streamlit_app.py
pkill -f "uvicorn app.api.main"

Then run:
conda activate forestgpt_trial
./scripts/dev.sh

It starts:
FastAPI: http://127.0.0.1:8003
Streamlit: http://127.0.0.1:8501

Start the app (FastAPI; Swagger)
from the project folder:

cd /Users/bennoeberhard/Projects/Exercise_Projects/mini_project_4/ForestGPT_trial
docker compose up -d?
python -m scripts.create_tables
uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8001 (8003, 8004...)


after schema (database, models, tables) changes:
python -m scripts.create_tables
for normal code changes:
uvicorn app.api.main:app --reload

For everyday work:
docker compose up -d
uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8003

Open Streamlit
streamlit run streamlit_app.py
(python -m streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8501)

fully stop Streamlit and restart:
pkill -f streamlit_app.py
python -m streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8501

fully stop FastAPI/uvicorn:
1. In the terminal where FastAPI is running:
Ctrl + C
2. uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8003 (or 8004...)

Streamlit runs here:
http://127.0.0.1:8501

Leaflet runs here:
http://127.0.0.1:8005/app/.
http://127.0.0.1:8005/app/

docker compose up -d (starts PostGIS)
uvicorn app.api.main:app --host 127.0.0.1 --port 8005 (starts the ForestGPT API + Leaflet frontend)
Then open:
http://127.0.0.1:8005/app/

It can:
- create a stand
- preview field defaults
- preview generated r3PG tables
- test chat

Inspect the parameters (to be found in scripts/r3pg_table_builder.R):
Rscript -e 'library(r3PG); print(get_parameters(mode="parameters", sp_names="Picea abies"))'


use the RAG pipeline
python -m scripts.create_tables
python -m scripts.ingest_rag_corpus

To rebuild the corpus
python -m scripts.ingest_rag_corpus --replace





# ForestGPT Trial

This is an early FastAPI backend for a forest manager decision-support app. It now has:

- PostGIS-backed stand records
- simulation run storage
- an r3PG simulation adapter through an Rscript bridge
- a yield-table based default value engine for field inputs
- document/chunk storage for RAG context
- a chat endpoint that combines stand data, simulation summaries, retrieved literature, and an OpenAI-compatible LLM

## Setup

Start PostGIS:

```bash
docker compose up -d
```

The Compose file exposes Postgres on host port `5433` by default to avoid collisions with an existing local Postgres. Override with `POSTGRES_HOST_PORT=5432 docker compose up -d` if you want the traditional port.

Install dependencies:

```bash
pip install -r requirements.txt
```

Create database tables:

```bash
python -m scripts.create_tables
```

Optionally seed one sample RAG document:

```bash
python -m scripts.seed_sample_document
```

Run the API:

```bash
uvicorn app.api.main:app --reload
```

For development, start PostGIS, FastAPI, and Streamlit together:

```bash
./scripts/dev.sh
```

This uses:

```text
FastAPI:   http://127.0.0.1:8003
Streamlit: http://127.0.0.1:8501
```

Override ports when needed:

```bash
API_PORT=8010 UI_PORT=8510 ./scripts/dev.sh
```

The launcher sets `FORESTGPT_API_URL` automatically, so Streamlit always calls the FastAPI port selected by the same command. Stop both development servers with `Ctrl+C`.

Open:

```text
http://127.0.0.1:8000/docs
```

## Example Flow

Create a stand:

```bash
curl -X POST http://127.0.0.1:8000/stands \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Beech stand A",
    "species": "European beech",
    "area_ha": 12.4,
    "age_years": 45,
    "properties": {"region": "Central Europe"}
  }'
```

Run a mock simulation:

```bash
curl -X POST http://127.0.0.1:8000/simulation-runs \
  -H "Content-Type: application/json" \
  -d '{
    "stand_id": 1,
    "species": "European beech",
    "initial_age_years": 45,
    "horizon_years": 20,
    "area_ha": 12.4,
    "initial_stems_per_ha": 620,
    "initial_basal_area_m2_ha": 24,
    "site_fertility": 0.7,
    "thinning_schedule": [{"year": 5, "removal_fraction": 0.18}]
  }'
```

The endpoint also accepts the newer generic adapter request format:

```bash
curl -X POST http://127.0.0.1:8001/simulation-runs \
  -H "Content-Type: application/json" \
  -d '{
    "stand_id": 1,
    "simulator": "mock",
    "input_mode": "simplified",
    "parameters": {
      "species": "European beech",
      "initial_age_years": 45,
      "horizon_years": 20,
      "area_ha": 12.4,
      "initial_stems_per_ha": 620,
      "initial_basal_area_m2_ha": 24,
      "site_fertility": 0.7,
      "thinning_schedule": [{"year": 5, "removal_fraction": 0.18}]
    }
  }'
```

List simulator adapters:

```bash
curl http://127.0.0.1:8001/simulation-runs/capabilities
```

## r3PG Adapter

The `r3PG` adapter is implemented as a Python-to-R bridge:

```text
app/simulation/adapters/r3pg_adapter.py
scripts/r3pg_runner.R
```

To use it, the machine or API container needs R with these packages:

```r
install.packages(c("jsonlite", "r3PG"))
```

Then set:

```bash
SIMULATION_ADAPTER=r3pg
```

or pass `"simulator": "r3pg"` in the simulation request. The current r3PG adapter expects raw r3PG input tables:

```json
{
  "stand_id": 1,
  "simulator": "r3pg",
  "input_mode": "r3pg_tables",
  "raw_inputs": {
    "site": [],
    "species": [],
    "climate": [],
    "thinning": [],
    "parameters": [],
    "size_dist": [],
    "settings": {
      "light_model": 2,
      "transp_model": 2,
      "phys_model": 2,
      "height_model": 1,
      "correct_bias": 0,
      "calculate_d13c": 0
    }
  }
}
```

The next step is to build a mapper from the app's simplified stand form to valid r3PG `site`, `species`, `climate`, `thinning`, `parameters`, and `size_dist` tables.

That mapper now exists for a first development path. It uses installed `r3PG` package defaults and currently supports the built-in example species, including:

- `European beech` / `Fagus sylvatica`
- `Scots pine` / `Pinus sylvestris`

Preview generated r3PG tables:

```bash
curl -X POST http://127.0.0.1:8001/simulation-runs/r3pg-tables \
  -H "Content-Type: application/json" \
  -d '{
    "stand_id": 1,
    "simulator": "r3pg",
    "input_mode": "simplified",
    "parameters": {
      "species": "European beech",
      "initial_age_years": 45,
      "horizon_years": 3,
      "initial_stems_per_ha": 620,
      "site_fertility": 0.7,
      "soil_water_capacity_mm": 120
    }
  }'
```

Run a real r3PG simulation from simplified app inputs:

```bash
curl -X POST http://127.0.0.1:8001/simulation-runs \
  -H "Content-Type: application/json" \
  -d '{
    "stand_id": 1,
    "simulator": "r3pg",
    "input_mode": "simplified",
    "parameters": {
      "species": "European beech",
      "initial_age_years": 45,
      "horizon_years": 3,
      "initial_stems_per_ha": 620,
      "site_fertility": 0.7,
      "soil_water_capacity_mm": 120
    }
  }'
```

The generated tables are scientifically provisional. Before real management use, validate parameter sets, climate data, species mapping, and output normalization for your target region and species.

The table builder uses `r3PG::get_parameters(...)` to access the package parameter library. You can inspect available parameter sets in R:

```bash
Rscript -e 'library(r3PG); print(get_parameters(mode = "overview"))'
```

You can force a specific parameter source by adding `parameter_set_id`:

```json
{
  "species": "European beech",
  "parameter_set_id": 29,
  "initial_age_years": 40,
  "horizon_years": 20,
  "initial_stems_per_ha": 620,
  "site_fertility": 0.7,
  "soil_water_capacity_mm": 120
}
```

If `parameter_set_id` is omitted, the builder chooses a matching species parameter set with usable `sizeDist` data, then includes the chosen source in the response metadata.

Ask the assistant:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "stand_id": 1,
    "simulation_run_id": 1,
    "question": "How should I manage this stand for the next 20 years?"
  }'
```

By default the chat endpoint expects an OpenAI-compatible server at `http://localhost:1234/v1`, matching the current `app/config.py` defaults.

By default the API expects PostGIS at:

```text
postgresql+psycopg://forestgpt_user:forestgpt_password@localhost:5433/forestgpt
```

Override this with `DATABASE_URL` when needed.






9.6.2026
Idea of generating a default value engine (kind of biomass preprocessor).
Input modes:
- Field Mode: minimal inputs, simple classes, suitable for smartphone use.
- Expert Mode: exact DBH, height, stem number, soil, climate, thinning values.
- Scientific Mode: full monthly climate, calibrated parameters, measured biomass, permanent plot data.
Implemented the first bottom-up field-input layer, with Norway spruce as the starting species.
Added:
- input-mode "field"
- transparent default engine

Example for Swagger
in: POST / simulation-runs/default-preview

{
  "stand_id": 3,
  "simulator": "r3pg",
  "input_mode": "field",
  "field_input": {
    "species": "Norway spruce",
    "age_years": 35,
    "stems_per_ha": 900,
    "altitude": 650,
    "soil_moisture": "mesic",
    "horizon_years": 5,
    "thinning_schedule": [
      {
        "year": 3,
        "removal_fraction": 0.2
      }
    ]
  }
}

Then run the same body in:
POST /simulation-runs

10.6.2026:
3 input modes: field, expert, scientific...
e.g. field: when a user leaves empty some fields e.g. he sets: Norway spruce, 80 years, altitude 1350m... but no stem number, the algorithm reverts to default values (for input mode "field" in: simulation/field_defaults.py). E.g. it takes missing stem numbers for spruce from d_species (see example script in R): beech, pine: 800, 800 (in d_species is no spruce). This is very vague. An escape option is to integrate a yield table adapter. See Word file "Generation of the app" chapter "Default values".

12.6.
Since almost (after 100 years some stems fail) no natural mortality occurs based on the provided parameters, these were modified for spruce.
age related mortality:
gammaN0, from 0 to 0.2
gammaN1, from 0 to 1.0
tgammaN, from 0 to 80
ngammaN, from 0 to 2

The override only affects the generated r3pg inputs, but leaves the package defaults untouched.

(density-dependent self-thinning:
wSx1000
thinPower
not modified)

18.6.
Added 2 more tree species: beech and larch
Enabled the simulation of mixed stands (not each species in parallel)
Updated the Streamlit interface

19.6.
Added the RAG pipeline
see: (script: scripts/ingest_rag_corpus.py)
hybrid score: BM25 + vector similarity
BM lexical retriever
vector cosine similarity retrieval when embeddings exist

Added memoryThe chat UI keeps a chat_session_id in Streamlit session state and sends it with follow-up questions, so the backend's existing conversation memory is reused.


# Plan py3PG app integration

I want to integrate the forest simulation model py3PG in this app. The idea is that a forest manager who has installed this app (once it is ready) on his smart phone, fills some required parameters and based on that runs a simulation with the forest growth simulation tool. In addition, via RAG I aim to integrate here domain-specific literature. An LLM will then be provided with all the the data (user query, top k relevant documents from the knowledge base, the simulation results, the memory, the system prompt...) in order to generate a useful answer to questions posed by the forest manager. E.g. he may ask (after running simulations related to that stand...): how should I manage this stand... for the next 20 years? py3PG is a Python library, so it should be possible to install it here.


Most backend files are still empty, but you already have the right early ingredients: FastAPI, PostGIS via Docker, `llama-index`, local/OpenAI-compatible LLM config, and placeholder folders for `geo`, `rag`, `llm`, and `simulation`.

Sources checked: [3-PG documentation](https://3pg.forestry.ubc.ca/documentation/), [3-PG model overview](https://3pg.forestry.ubc.ca/model-developers/), [r3PG GitHub](https://github.com/trotsiuk/r3PG), [r3PG docs](https://www.rdocumentation.org/packages/r3PG/versions/0.1.6), [3-PG2Py paper](https://www.sciencedirect.com/science/article/pii/S1364815222000640).

**Target Architecture**

The app should have four main layers:

1. **Mobile client**
   Forest manager enters stand data, selects species/site/climate/management scenario, runs simulations, and asks questions.

2. **FastAPI backend**
   Owns authentication, stand records, simulation requests, RAG retrieval, LLM orchestration, and saved conversations.

3. **Simulation service**
   A Python module wrapping the 3-PG implementation behind a stable internal API:

   ```python
   run_growth_simulation(input: SimulationInput) -> SimulationResult
   ```

4. **Knowledge + memory layer**
   Literature PDFs, guidelines, local management documents, prior stand records, prior conversations, and simulation outputs become retrievable context for the LLM.

**Core User Flow**

1. Manager creates or opens a forest stand.
2. App asks for required simulation inputs:
   species, stand age, stocking/stems per ha, basal area or biomass, site fertility, soil water capacity, latitude/elevation, climate data source, simulation horizon, thinning/harvest assumptions.
3. Backend validates and normalizes input.
4. Simulation module runs 3-PG/py3PG.
5. Results are stored as structured monthly/yearly outputs.
6. Manager asks: “How should I manage this stand for the next 20 years?”
7. RAG retrieves relevant documents.
8. LLM receives:
   user query,
   stand profile,
   simulation results,
   relevant literature,
   prior memory,
   system prompt with safety/uncertainty rules.
9. App returns an answer with recommendations, assumptions, caveats, and cited sources.

**Implementation Phases**

**Phase 1: Foundation**

Build the backend skeleton first.

Recommended modules:

```text
app/
  api/
    main.py
  geo/
    db.py
    models.py
    routes.py
  simulation/
    schemas.py
    service.py
    adapters/
      base.py
      r3pg_adapter.py
  rag/
    ingest.py
    index.py
    retrieve.py
  llm/
    prompts.py
    service.py
  memory/
    service.py
```

Add database tables for:

```text
stands
simulation_runs
simulation_outputs
documents
document_chunks
chat_sessions
chat_messages
```

Use the existing PostGIS container for stand geometry and spatial queries.

**Phase 2: Simulation Spike**

Before building UI around py3PG, test:

1. Can the exact package be installed?
2. What are the required input tables/objects?
3. What species parameter sets are available?
4. Does it support mixed species, uneven-aged stands, thinning, climate scenarios?
5. What output variables does it return?

If py3PG is not reliable, use the adapter pattern and start with either:

- `3-PG2Py` if installable and adequate,
- `r3PG` through an R subprocess/container,
- or a mock simulator for frontend/RAG development while the scientific model integration is clarified.

**Phase 3: Simulation API**

Expose endpoints like:

```text
POST /stands
GET /stands/{stand_id}
POST /simulation-runs
GET /simulation-runs/{run_id}
GET /stands/{stand_id}/simulation-runs
```

A simulation request should be stored with all inputs, model version, parameter set, climate source, and timestamp. This matters because forest advice must be reproducible.

**Phase 4: RAG Pipeline**

Create an ingestion script for PDFs and documents:

```text
data/literature/
storage/index/
```

Use `llama-index`, already in `requirements.txt`, to:

1. Load PDFs.
2. Chunk by section/paragraph.
3. Attach metadata:
   title, author, year, region, species, topic, source path.
4. Generate embeddings.
5. Store a persistent vector index.

Retrieval should support filters like:

```text
species = beech
region = Central Europe
topic = thinning
stand_type = even-aged
```

This will prevent the LLM from pulling generic or irrelevant forestry advice.

**Phase 5: LLM Orchestration**

Create one central service that builds the final prompt. It should include:

```text
System prompt:
- You are a forestry decision-support assistant.
- Use simulation results and cited literature.
- State assumptions.
- Do not overstate certainty.
- Distinguish model output from management recommendation.
- Recommend consulting local regulations/professionals for binding decisions.

Context:
- Stand profile
- Simulation summary
- Retrieved documents
- Conversation memory
- User question
```

The answer format should probably be structured:

```text
Summary recommendation
Expected stand development
Management options
Risks and uncertainties
What data would improve the answer
Sources used
```

**Phase 6: Mobile App**

For the smartphone app, I would not put py3PG on-device initially. Keep the simulation and RAG on the backend.

Recommended options:

- Fastest path: responsive web app/PWA.
- More app-like path: React Native or Expo.
- Backend remains FastAPI either way.

Main screens:

```text
Stand Map
Stand Detail
Simulation Setup
Simulation Results
Ask Assistant
Document Library
Settings
```

For forest managers, the UI should be field-friendly: large controls, offline draft saving, map-first navigation, minimal typing, sensible defaults, and clear validation.

**Phase 7: Scientific Guardrails**

This app should be careful because it produces management guidance. Add guardrails early:

- Always show model assumptions.
- Store model version and parameter source.
- Cite retrieved literature.
- Flag missing inputs.
- Use confidence/uncertainty language.
- Never let the LLM invent simulation results.
- Prefer “scenario comparison” over single prescriptive answers.

Example scenarios:

```text
No thinning
Moderate thinning every 5 years
Heavy thinning at year 10
Climate stress scenario
Short rotation vs long rotation
```

**MVP Scope**

A strong MVP would be:

1. FastAPI backend with PostGIS.
2. Stand creation and retrieval.
3. One working simulation adapter.
4. One hardcoded species/site parameter example.
5. PDF ingestion into RAG.
6. Chat endpoint that combines query + retrieved docs + simulation result.
7. Simple mobile-friendly web UI.

After that, expand to real species libraries, climate data integrations, management scenarios, map editing, authentication, and offline support.

**Biggest Risks**

The main risk is not the LLM or FastAPI. It is scientific/data validity: 3-PG requires careful parameterization, climate inputs, soil/site assumptions, and species-specific calibration. The second risk is dependency uncertainty around the exact Python package. So I’d start with the simulation spike, then lock the internal adapter API before building the rest.
