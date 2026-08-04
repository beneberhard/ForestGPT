import json
import subprocess
import tempfile
from pathlib import Path

from app.simulation.r3pg_tables import build_r3pg_tables
from app.simulation.schemas import GrowthSimulationRequest


def main():
    req = GrowthSimulationRequest(
        stand_id=1,
        simulator="r3pg",
        input_mode="simplified",
        parameters={
            "species": "Fagus sylvatica",
            "initial_age_years": 40,
            "horizon_years": 20,
            "initial_stems_per_ha": 800,
            "site_fertility": 0.65,
            "thinning_schedule": [{"year": 5, "removal_fraction": 0.18, "species": "Fagus sylvatica"}],
        },
    )

    print("Building r3PG tables...")
    tables = build_r3pg_tables(req)
    payload = {"raw_inputs": tables, "parameters": req.parameters}

    with tempfile.TemporaryDirectory(prefix="forestgpt_r3pg_run_") as tmp:
        input_path = Path(tmp) / "input.json"
        output_path = Path(tmp) / "output.json"
        input_path.write_text(json.dumps(payload), encoding="utf-8")

        print(f"Running R runner: scripts/r3pg_runner.R -> output at {output_path}")
        proc = subprocess.run(["Rscript", "scripts/r3pg_runner.R", str(input_path), str(output_path)], capture_output=True, text=True)
        print("R stdout:")
        print(proc.stdout)
        print("R stderr:")
        print(proc.stderr)
        if proc.returncode != 0:
            print("r3PG runner exited with non-zero status", proc.returncode)
            return

        result = json.loads(output_path.read_text(encoding="utf-8"))
        print("Result summary:")
        print(json.dumps(result.get("summary", {}), indent=2))
        print("Annual outputs sample:")
        for row in result.get("annual_outputs", [])[:6]:
            print(row)


if __name__ == "__main__":
    main()
