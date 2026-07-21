from openai import OpenAI, OpenAIError
from sqlalchemy import text
from sqlalchemy.orm import Session, selectinload

from app.config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MAX_TOKENS, OPENAI_MODEL
from app.geo.models import ChatMessage, ChatSession, SimulationRun, Stand, StandObservation
from app.llm.prompts import SYSTEM_PROMPT, build_context_prompt
from app.llm.schemas import ChatRequest, ChatResponse
from app.rag.retrieve import retrieve_relevant_chunks
from app.spatial.terrain import terrain_summary_for_stand


def answer_manager_question(db: Session, payload: ChatRequest) -> ChatResponse:
    session = _get_or_create_session(db, payload)
    stand = db.get(Stand, payload.stand_id) if payload.stand_id else None
    simulations = _simulation_context_runs(db, payload)
    retrieved = retrieve_relevant_chunks(db, payload.question, payload.top_k)
    memory = _recent_memory(session)

    stand_context = _stand_context(db, stand)
    retrieved_context = [_compact_chunk(chunk.model_dump()) for chunk in retrieved]
    simulation_summary = _compact_simulation_context(simulations)

    prompt = build_context_prompt(
        question=payload.question,
        stand_context=stand_context,
        simulation_summary=simulation_summary,
        retrieved_chunks=retrieved_context,
        memory=memory,
    )
    min_retrieved_chunks = min(6, len(retrieved_context))
    while len(prompt) > 60000 and len(retrieved_context) > min_retrieved_chunks:
        retrieved_context = retrieved_context[:-1]
        prompt = build_context_prompt(
            question=payload.question,
            stand_context=stand_context,
            simulation_summary=simulation_summary,
            retrieved_chunks=retrieved_context,
            memory=memory,
        )
    answer = _call_llm(prompt)
    answer = _ensure_rag_sources_reported(answer, retrieved_context)
    answer = _ensure_memory_source_reported(answer, memory)

    db.add(ChatMessage(session_id=session.id, role="user", content=payload.question))
    db.add(
        ChatMessage(
            session_id=session.id,
            role="assistant",
            content=answer,
            metadata_json={
                "stand_id": payload.stand_id,
                "simulation_run_id": payload.simulation_run_id,
                "simulation_run_ids": [run.id for run in simulations],
                "retrieved_context": retrieved_context,
            },
        )
    )
    db.commit()

    return ChatResponse(
        session_id=session.id,
        answer=answer,
        retrieved_context=retrieved_context,
        simulation_summary=simulation_summary,
    )


def _simulation_context_runs(db: Session, payload: ChatRequest) -> list[SimulationRun]:
    run_ids = []
    if payload.simulation_run_id:
        run_ids.append(payload.simulation_run_id)
    run_ids.extend(payload.simulation_run_ids or [])

    unique_ids = []
    for run_id in run_ids:
        if run_id not in unique_ids:
            unique_ids.append(run_id)
    if not unique_ids:
        return []

    runs = (
        db.query(SimulationRun)
        .options(selectinload(SimulationRun.outputs))
        .filter(SimulationRun.id.in_(unique_ids[:8]))
        .all()
    )
    by_id = {run.id: run for run in runs}
    return [by_id[run_id] for run_id in unique_ids if run_id in by_id]


def _get_or_create_session(db: Session, payload: ChatRequest) -> ChatSession:
    if payload.session_id:
        session = db.get(ChatSession, payload.session_id)
        if session:
            return session

    session = ChatSession(stand_id=payload.stand_id, title=payload.question[:120])
    db.add(session)
    db.flush()
    return session


def _recent_memory(session: ChatSession, limit: int = 4) -> list[dict]:
    messages = sorted(session.messages, key=lambda message: message.created_at)[-limit:]
    return [{"role": message.role, "content": _truncate(message.content, 600)} for message in messages]


def _stand_context(db: Session, stand: Stand | None) -> dict | None:
    if stand is None:
        return None
    return {
        "id": stand.id,
        "name": stand.name,
        "species": stand.species,
        "area_ha": stand.area_ha,
        "age_years": stand.age_years,
        "properties": stand.properties,
        "spatial_summary": _stand_spatial_summary(db, stand.id),
        "nearby_forest_roads": _nearby_forest_roads_summary(db, stand.id),
        "terrain_summary": terrain_summary_for_stand(db, stand.id),
        "field_observations": _field_observations_context(db, stand.id),
    }


def _field_observations_context(db: Session, stand_id: int) -> list[dict]:
    observations = (
        db.query(StandObservation)
        .filter(StandObservation.stand_id == stand_id)
        .order_by(StandObservation.observed_at.desc(), StandObservation.id.desc())
        .all()
    )
    return [
        {
            "observed_at": observation.observed_at.isoformat() if observation.observed_at else None,
            "observer": observation.observer,
            "category": observation.category,
            "note": _truncate(observation.note, 500),
            "properties": observation.properties,
        }
        for observation in observations
    ]


def _stand_spatial_summary(db: Session, stand_id: int) -> dict | None:
    row = db.execute(
        text(
            """
            SELECT
                ST_GeometryType(geometry) AS geometry_type,
                ST_IsValid(geometry) AS is_valid,
                ROUND((ST_Area(geometry::geography) / 10000.0)::numeric, 3) AS area_ha_geodesic,
                ROUND(ST_Perimeter(geometry::geography)::numeric, 1) AS perimeter_m,
                ROUND(ST_X(ST_Centroid(geometry))::numeric, 6) AS centroid_lon,
                ROUND(ST_Y(ST_Centroid(geometry))::numeric, 6) AS centroid_lat,
                ROUND(ST_XMin(ST_Envelope(geometry))::numeric, 6) AS bbox_min_lon,
                ROUND(ST_YMin(ST_Envelope(geometry))::numeric, 6) AS bbox_min_lat,
                ROUND(ST_XMax(ST_Envelope(geometry))::numeric, 6) AS bbox_max_lon,
                ROUND(ST_YMax(ST_Envelope(geometry))::numeric, 6) AS bbox_max_lat
            FROM stands
            WHERE id = :stand_id
              AND geometry IS NOT NULL
            """
        ),
        {"stand_id": stand_id},
    ).mappings().first()
    if row is None:
        return None
    return {
        "geometry_type": row["geometry_type"],
        "is_valid": row["is_valid"],
        "area_ha_geodesic": float(row["area_ha_geodesic"]) if row["area_ha_geodesic"] is not None else None,
        "perimeter_m": float(row["perimeter_m"]) if row["perimeter_m"] is not None else None,
        "centroid": {
            "lon": float(row["centroid_lon"]),
            "lat": float(row["centroid_lat"]),
        },
        "bbox": {
            "min_lon": float(row["bbox_min_lon"]),
            "min_lat": float(row["bbox_min_lat"]),
            "max_lon": float(row["bbox_max_lon"]),
            "max_lat": float(row["bbox_max_lat"]),
        },
    }


def _nearby_forest_roads_summary(db: Session, stand_id: int) -> dict | None:
    layers = _road_layers(db)
    if not layers:
        return None

    layer_summaries = []
    nearest_features = []
    for layer in layers:
        summary = _road_layer_summary(db, stand_id, layer)
        if summary:
            layer_summaries.append(summary)
            nearest_features.extend(summary["nearest_features"])

    if not layer_summaries:
        return None

    nearest_features = sorted(
        nearest_features,
        key=lambda feature: feature["distance_m"] if feature["distance_m"] is not None else float("inf"),
    )[:8]
    road_length_within_250m = sum(summary["road_length_within_250m_m"] or 0 for summary in layer_summaries)
    road_length_within_500m = sum(summary["road_length_within_500m_m"] or 0 for summary in layer_summaries)
    nearest_distance = min(
        (summary["nearest_distance_m"] for summary in layer_summaries if summary["nearest_distance_m"] is not None),
        default=None,
    )

    return {
        "total_features": sum(summary["total_features"] for summary in layer_summaries),
        "counts_by_distance": {
            "within_50m": sum(summary["counts_by_distance"]["within_50m"] for summary in layer_summaries),
            "within_100m": sum(summary["counts_by_distance"]["within_100m"] for summary in layer_summaries),
            "within_250m": sum(summary["counts_by_distance"]["within_250m"] for summary in layer_summaries),
            "within_500m": sum(summary["counts_by_distance"]["within_500m"] for summary in layer_summaries),
        },
        "nearest_distance_m": nearest_distance,
        "road_length_within_250m_m": round(road_length_within_250m, 1),
        "road_length_within_500m_m": round(road_length_within_500m, 1),
        "nearest_features": nearest_features,
        "layers": layer_summaries,
    }


def _road_layers(db: Session) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT
                f_table_schema AS schema_name,
                f_table_name AS table_name,
                f_geometry_column AS geometry_column
            FROM geometry_columns
            WHERE f_table_schema = 'public'
              AND lower(f_table_name) LIKE '%road%'
              AND upper(type) LIKE '%LINE%'
            ORDER BY f_table_name
            """
        )
    ).mappings()
    return [dict(row) for row in rows]


def _road_layer_summary(db: Session, stand_id: int, layer: dict) -> dict | None:
    schema = layer["schema_name"]
    table = layer["table_name"]
    geom = layer["geometry_column"]
    for value, field in ((schema, "schema"), (table, "table"), (geom, "geometry_column")):
        _validate_identifier(value, field)
    columns = _table_columns(db, schema, table)
    id_expr = _column_expr(columns, "id", fallback="fid")
    highway_expr = _column_expr(columns, "highway")
    motor_vehicle_expr = _column_expr(columns, "motor_vehicle")
    smoothness_expr = _column_expr(columns, "smoothness")
    tracktype_expr = _column_expr(columns, "tracktype")
    surface_expr = _column_expr(columns, "surface")
    name_expr = _column_expr(columns, "name")
    geom_expr = f'ST_Transform(r."{geom}", 4326)'

    summary = db.execute(
        text(
            f"""
            WITH distances AS (
                SELECT
                    {id_expr} AS id,
                    ST_Distance({geom_expr}::geography, s.geometry::geography) AS distance_m,
                    ST_Length({geom_expr}::geography) AS length_m
                FROM "{schema}"."{table}" r
                JOIN stands s ON s.id = :stand_id
                WHERE s.geometry IS NOT NULL
                  AND r."{geom}" IS NOT NULL
            )
            SELECT
                COUNT(*) AS total_features,
                COUNT(*) FILTER (WHERE distance_m <= 50) AS within_50m,
                COUNT(*) FILTER (WHERE distance_m <= 100) AS within_100m,
                COUNT(*) FILTER (WHERE distance_m <= 250) AS within_250m,
                COUNT(*) FILTER (WHERE distance_m <= 500) AS within_500m,
                ROUND(MIN(distance_m)::numeric, 1) AS nearest_distance_m,
                ROUND(SUM(length_m) FILTER (WHERE distance_m <= 250)::numeric, 1) AS road_length_within_250m_m,
                ROUND(SUM(length_m) FILTER (WHERE distance_m <= 500)::numeric, 1) AS road_length_within_500m_m
            FROM distances
            """
        ),
        {"stand_id": stand_id},
    ).mappings().first()
    if summary is None or summary["total_features"] == 0:
        return None
    if int(summary["within_500m"]) == 0:
        return None

    nearest = db.execute(
        text(
            f"""
            SELECT
                {id_expr} AS id,
                {name_expr} AS name,
                {highway_expr} AS highway,
                {motor_vehicle_expr} AS motor_vehicle,
                {smoothness_expr} AS smoothness,
                {tracktype_expr} AS tracktype,
                {surface_expr} AS surface,
                ROUND(ST_Distance({geom_expr}::geography, s.geometry::geography)::numeric, 1) AS distance_m,
                ROUND(ST_Length({geom_expr}::geography)::numeric, 1) AS length_m,
                ST_Intersects({geom_expr}, s.geometry) AS intersects_stand
            FROM "{schema}"."{table}" r
            JOIN stands s ON s.id = :stand_id
            WHERE s.geometry IS NOT NULL
              AND r."{geom}" IS NOT NULL
            ORDER BY ST_Distance({geom_expr}::geography, s.geometry::geography)
            LIMIT 5
            """
        ),
        {"stand_id": stand_id},
    ).mappings()

    return {
        "source_table": table,
        "total_features": int(summary["total_features"]),
        "counts_by_distance": {
            "within_50m": int(summary["within_50m"]),
            "within_100m": int(summary["within_100m"]),
            "within_250m": int(summary["within_250m"]),
            "within_500m": int(summary["within_500m"]),
        },
        "nearest_distance_m": _float_or_none(summary["nearest_distance_m"]),
        "road_length_within_250m_m": _float_or_none(summary["road_length_within_250m_m"]),
        "road_length_within_500m_m": _float_or_none(summary["road_length_within_500m_m"]),
        "nearest_features": [
            {
                "source_table": table,
                "id": row["id"],
                "name": row["name"],
                "highway": row["highway"],
                "surface": row["surface"],
                "tracktype": row["tracktype"],
                "smoothness": row["smoothness"],
                "motor_vehicle": row["motor_vehicle"],
                "distance_m": _float_or_none(row["distance_m"]),
                "length_m": _float_or_none(row["length_m"]),
                "intersects_stand": row["intersects_stand"],
            }
            for row in nearest
        ],
    }


def _validate_identifier(identifier: str, field_name: str) -> None:
    if not identifier or not identifier.replace("_", "").isalnum() or identifier[0].isdigit():
        raise ValueError(f"Invalid {field_name}: {identifier}")


def _table_columns(db: Session, schema: str, table: str) -> set[str]:
    rows = db.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = :schema
              AND table_name = :table
            """
        ),
        {"schema": schema, "table": table},
    )
    return {row[0] for row in rows}


def _column_expr(columns: set[str], preferred: str, fallback: str | None = None) -> str:
    if preferred in columns:
        return f'r."{preferred}"'
    if fallback and fallback in columns:
        return f'r."{fallback}"'
    return "NULL"


def _float_or_none(value: object) -> float | None:
    return float(value) if value is not None else None


def _call_llm(prompt: str) -> str:
    client = OpenAI(base_url=OPENAI_BASE_URL, api_key=OPENAI_API_KEY)
    content = _complete(client, prompt, OPENAI_MAX_TOKENS)
    if content:
        return content
    retry_prompt = f"""Write the final answer only. Do not show reasoning. Do not quote context.
Use this context briefly and synthesize it into a practical forestry answer:

{_truncate(prompt, 5000)}
"""
    content = _complete(client, retry_prompt, max(OPENAI_MAX_TOKENS, 2048))
    return content or "The local model returned no final answer. Try a shorter question or a larger LM Studio context/output limit."


def _complete(client: OpenAI, prompt: str, max_tokens: int) -> str | None:
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=max_tokens,
        )
    except OpenAIError as exc:
        raise RuntimeError(f"LLM server not reachable or rejected the request: {exc}") from exc
    content = response.choices[0].message.content
    return content.strip() if content else None


def _compact_chunk(chunk: dict) -> dict:
    return {
        "title": chunk.get("title"),
        "score": chunk.get("score"),
        "chunk_text": _truncate(chunk.get("chunk_text") or "", 700),
    }


def _ensure_rag_sources_reported(answer: str, retrieved_context: list[dict]) -> str:
    if not retrieved_context:
        return answer

    titles = []
    for chunk in retrieved_context:
        title = chunk.get("title")
        if title and title not in titles:
            titles.append(title)
    if not titles:
        return answer
    answer_lower = answer.lower()
    if "rag text corpus" in answer_lower and any(title.lower() in answer_lower for title in titles):
        return answer

    return f"{answer.rstrip()}\n\nRAG text corpus: {', '.join(titles)}"


def _ensure_memory_source_reported(answer: str, memory: list[dict]) -> str:
    if not memory:
        return answer
    answer_lower = answer.lower()
    if "previous conversation" in answer_lower or "conversation memory" in answer_lower:
        return answer
    return f"{answer.rstrip()}\n\nPrevious conversation: recent messages in this chat session"


def _compact_simulation_summary(summary: dict | None) -> dict | None:
    if not summary:
        return None
    compact = {
        "warning": summary.get("warning"),
        "sanity_warnings": summary.get("sanity_warnings"),
        "resolved_thinning": summary.get("resolved_thinning"),
    }
    diagnostics = summary.get("diagnostics") or []
    if diagnostics:
        compact["diagnostics_first_rows"] = diagnostics[:6]
        compact["diagnostics_last_rows"] = diagnostics[-6:] if len(diagnostics) > 6 else []
    field_defaults = summary.get("field_defaults") or {}
    completed = field_defaults.get("completed_parameters") or {}
    if completed:
        compact["field_input"] = {
            key: completed.get(key)
            for key in ("species_entries", "horizon_years", "site_fertility", "soil_water_capacity_mm", "thinning_schedule")
            if key in completed
        }
    return {key: value for key, value in compact.items() if value}


def _compact_simulation_context(runs: list[SimulationRun]) -> dict | None:
    if not runs:
        return None
    compact_runs = [_compact_simulation_run(run) for run in runs]
    return {
        "selected_run_count": len(compact_runs),
        "runs": compact_runs,
        "comparison_note": "Compare runs by their IDs. Use outputs_first_rows and outputs_last_rows to compare early and final development.",
    }


def _compact_simulation_run(run: SimulationRun) -> dict:
    outputs = sorted(run.outputs, key=lambda output: output.year)
    output_rows = [output.output for output in outputs]
    return {
        "run_id": run.id,
        "stand_id": run.stand_id,
        "model_name": run.model_name,
        "model_version": run.model_version,
        "status": run.status,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "input_parameters": _compact_run_input(run.input_parameters),
        "summary": _compact_simulation_summary(run.summary),
        "outputs_first_rows": output_rows[:4],
        "outputs_last_rows": output_rows[-8:] if len(output_rows) > 4 else [],
    }


def _compact_run_input(input_parameters: dict | None) -> dict:
    if not input_parameters:
        return {}
    field_input = input_parameters.get("field_input") or {}
    return {
        "input_mode": input_parameters.get("input_mode"),
        "field_input": {
            key: field_input.get(key)
            for key in ("altitude", "soil_moisture", "site_fertility", "horizon_years", "species_entries", "thinning_schedule")
            if key in field_input
        },
    }


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + " [...]"
