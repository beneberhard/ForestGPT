from datetime import datetime

from sqlalchemy.orm import Session

from app.config import SIMULATION_ADAPTER
from app.geo.models import SimulationOutput, SimulationRun
from app.simulation.adapters.base import SimulationAdapter
from app.simulation.adapters.r3pg_adapter import R3PGAdapter
from app.simulation.schemas import GrowthSimulationRequest, SimulatorCapability


def get_simulation_adapter(adapter_key: str | None = None) -> SimulationAdapter:
    selected = adapter_key or SIMULATION_ADAPTER
    if selected == "r3pg":
        return R3PGAdapter()
    raise ValueError(f"Unsupported simulator: {selected}. Use 'r3pg'.")


def list_simulation_capabilities() -> list[SimulatorCapability]:
    return [R3PGAdapter().capability()]


def run_and_store_simulation(db: Session, request: GrowthSimulationRequest) -> SimulationRun:
    adapter = get_simulation_adapter(request.simulator)
    run = SimulationRun(
        stand_id=request.stand_id,
        model_name=adapter.model_name,
        model_version=adapter.model_version,
        input_parameters=request.model_dump(),
        status="running",
    )
    db.add(run)
    db.flush()

    try:
        result = adapter.run(request)
        run.status = "completed"
        run.model_name = result.model_name
        run.model_version = result.model_version
        run.summary = result.summary
        run.completed_at = datetime.utcnow()
        for output in result.outputs:
            db.add(
                SimulationOutput(
                    run_id=run.id,
                    year=output.year,
                    output=output.model_dump(),
                )
            )
    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)
        run.completed_at = datetime.utcnow()
        db.commit()
        raise

    db.commit()
    db.refresh(run)
    return run
