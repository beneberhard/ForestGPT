import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from app.config import R3PG_TABLE_BUILDER_PATH, RSCRIPT_BIN
from app.simulation.schemas import GrowthSimulationRequest


def build_r3pg_tables(request: GrowthSimulationRequest) -> dict[str, Any]:
    if shutil.which(RSCRIPT_BIN) is None:
        raise RuntimeError(
            f"Cannot build r3PG tables because '{RSCRIPT_BIN}' is not available on PATH. "
            "Install R/Rscript or set RSCRIPT_BIN."
        )

    builder = Path(R3PG_TABLE_BUILDER_PATH)
    if not builder.exists():
        raise RuntimeError(f"r3PG table builder script not found: {builder}")

    payload = request.model_dump()
    with tempfile.TemporaryDirectory(prefix="forestgpt_r3pg_tables_") as tmp_dir:
        input_path = Path(tmp_dir) / "input.json"
        output_path = Path(tmp_dir) / "output.json"
        input_path.write_text(json.dumps(payload), encoding="utf-8")

        completed = subprocess.run(
            [RSCRIPT_BIN, str(builder), str(input_path), str(output_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "r3PG table builder failed.\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            )
        return json.loads(output_path.read_text(encoding="utf-8"))
