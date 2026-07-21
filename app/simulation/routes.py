import csv
import io
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session, selectinload

from app.geo.db import get_db
from app.geo.models import SimulationRun, Stand
from app.simulation.field_defaults import complete_field_input
from app.simulation.r3pg_tables import build_r3pg_tables
from app.simulation.schemas import FieldDefaultPreview, GrowthSimulationRequest, SimulationRunRead, SimulatorCapability
from app.simulation.service import (
    list_simulation_capabilities,
    run_and_store_simulation,
)

router = APIRouter(prefix="/simulation-runs", tags=["simulation"])


@router.get("/capabilities", response_model=list[SimulatorCapability])
def get_simulation_capabilities() -> list[SimulatorCapability]:
    return list_simulation_capabilities()


@router.post("/r3pg-tables")
def build_r3pg_input_tables(payload: dict[str, Any]) -> dict[str, Any]:
    request = _parse_simulation_request(payload)
    if request.input_mode == "field":
        preview = complete_field_input(request)
        request = GrowthSimulationRequest(
            stand_id=request.stand_id,
            simulator=request.simulator,
            input_mode="simplified",
            parameters=preview.completed_parameters,
            field_input=request.field_input,
        )
    if request.input_mode != "simplified":
        raise HTTPException(status_code=400, detail="Use input_mode='field' or 'simplified' to build r3PG tables.")
    return build_r3pg_tables(request)


@router.post("/default-preview", response_model=FieldDefaultPreview)
def preview_field_defaults(payload: dict[str, Any]) -> FieldDefaultPreview:
    request = _parse_simulation_request(payload)
    if request.input_mode != "field":
        raise HTTPException(status_code=400, detail="Use input_mode='field' for default preview.")
    preview = complete_field_input(request)
    table_request = GrowthSimulationRequest(
        stand_id=request.stand_id,
        simulator=request.simulator,
        input_mode="simplified",
        parameters=preview.completed_parameters,
        field_input=request.field_input,
    )
    preview.r3pg_tables = build_r3pg_tables(table_request)
    return preview


@router.post("", response_model=SimulationRunRead)
def create_simulation_run(payload: dict[str, Any], db: Session = Depends(get_db)) -> SimulationRun:
    request = _parse_simulation_request(payload)
    if request.stand_id is not None:
        stand = db.get(Stand, request.stand_id)
        if stand is None:
            raise HTTPException(status_code=404, detail="Stand not found")
    return run_and_store_simulation(db, request)


@router.get("/stand/{stand_id}", response_model=list[SimulationRunRead])
def list_stand_simulation_runs(stand_id: int, db: Session = Depends(get_db)) -> list[SimulationRun]:
    return (
        db.query(SimulationRun)
        .options(selectinload(SimulationRun.outputs))
        .filter(SimulationRun.stand_id == stand_id)
        .order_by(SimulationRun.created_at.desc())
        .all()
    )


@router.get("/{run_id}", response_model=SimulationRunRead)
def get_simulation_run(run_id: int, db: Session = Depends(get_db)) -> SimulationRun:
    run = (
        db.query(SimulationRun)
        .options(selectinload(SimulationRun.outputs))
        .filter(SimulationRun.id == run_id)
        .first()
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    return run


@router.get("/{run_id}/outputs.csv")
def download_simulation_outputs_csv(run_id: int, db: Session = Depends(get_db)) -> Response:
    run = (
        db.query(SimulationRun)
        .options(selectinload(SimulationRun.outputs))
        .filter(SimulationRun.id == run_id)
        .first()
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Simulation run not found")

    metadata_keys = {
        "run_id",
        "stand_id",
        "model_name",
        "model_version",
        "status",
        "created_at",
        "completed_at",
        "year",
    }
    output_keys = sorted(
        {
            key
            for output in run.outputs
            for key in (output.output or {}).keys()
            if key not in metadata_keys
        }
    )
    fieldnames = [
        "run_id",
        "stand_id",
        "model_name",
        "model_version",
        "status",
        "created_at",
        "completed_at",
        "year",
        *output_keys,
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for output in sorted(run.outputs, key=lambda item: (item.year, str((item.output or {}).get("species", "")))):
        row = {
            "run_id": run.id,
            "stand_id": run.stand_id,
            "model_name": run.model_name,
            "model_version": run.model_version,
            "status": run.status,
            "created_at": run.created_at.isoformat() if run.created_at else "",
            "completed_at": run.completed_at.isoformat() if run.completed_at else "",
            "year": output.year,
            **(output.output or {}),
        }
        row["year"] = output.year
        writer.writerow({key: _csv_value(value) for key, value in row.items()})

    filename = f"forestgpt_simulation_run_{run.id}_outputs.csv"
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{run_id}")
def delete_simulation_run(run_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    run = db.get(SimulationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    db.delete(run)
    db.commit()
    return {"deleted": True, "id": run_id}


def _parse_simulation_request(payload: dict[str, Any]) -> GrowthSimulationRequest:
    return GrowthSimulationRequest(**payload)


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=True)
    return value
