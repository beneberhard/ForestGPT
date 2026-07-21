import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from app.config import R3PG_RUNNER_PATH, RSCRIPT_BIN
from app.simulation.adapters.base import SimulationAdapter
from app.simulation.field_defaults import complete_field_input
from app.simulation.r3pg_tables import build_r3pg_tables
from app.simulation.schemas import AnnualSimulationOutput, GrowthSimulationRequest, SimulationResult, SimulatorCapability


class R3PGAdapter(SimulationAdapter):
    adapter_key = "r3pg"
    model_name = "r3PG"
    model_version = None

    def capability(self) -> SimulatorCapability:
        return SimulatorCapability(
            name=self.model_name,
            version=self.model_version,
            description="R r3PG adapter using run_3PG through an Rscript JSON bridge.",
            input_modes=["field", "simplified", "r3pg_tables"],
            output_frequency="monthly_raw_annual_normalized",
            supports_mixtures=True,
            supports_thinning=True,
            requires_external_runtime="R + R packages r3PG and jsonlite",
        )

    def run(self, request: GrowthSimulationRequest) -> SimulationResult:
        field_default_context = None
        input_volume: float | dict[str, float] | None = None
        input_stems: float | dict[str, float] | None = None
        if request.input_mode == "field":
            preview = complete_field_input(request)
            species_entries = preview.completed_parameters.get("species_entries", [])
            if species_entries:
                input_volume = {
                    entry["species"]: _optional_float(entry.get("volume_m3_ha"))
                    for entry in species_entries
                    if entry.get("volume_m3_ha") is not None
                }
                input_stems = {
                    entry["species"]: _optional_float(entry.get("initial_stems_per_ha"))
                    for entry in species_entries
                    if entry.get("initial_stems_per_ha") is not None
                }
            else:
                input_volume = _optional_float(preview.completed_parameters.get("volume_m3_ha"))
                input_stems = _optional_float(preview.completed_parameters.get("initial_stems_per_ha"))
            field_default_context = {
                "completed_parameters": preview.completed_parameters,
                "assumptions": [assumption.model_dump() for assumption in preview.assumptions],
                "warnings": preview.warnings,
            }
            request = GrowthSimulationRequest(
                stand_id=request.stand_id,
                simulator=request.simulator,
                input_mode="simplified",
                parameters={
                    **preview.completed_parameters,
                    "_default_assumptions": field_default_context["assumptions"],
                    "_default_warnings": field_default_context["warnings"],
                },
                field_input=request.field_input,
            )

        if request.input_mode == "simplified":
            built_tables = build_r3pg_tables(request)
            request = GrowthSimulationRequest(
                stand_id=request.stand_id,
                simulator=request.simulator,
                input_mode="r3pg_tables",
                parameters=request.parameters,
                raw_inputs=built_tables,
            )
        elif request.input_mode != "r3pg_tables":
            raise ValueError("r3PG adapter requires input_mode='field', 'simplified', or 'r3pg_tables'.")
        if shutil.which(RSCRIPT_BIN) is None:
            raise RuntimeError(
                f"Cannot run r3PG because '{RSCRIPT_BIN}' is not available on PATH. "
                "Install R/Rscript or set RSCRIPT_BIN."
            )

        runner = Path(R3PG_RUNNER_PATH)
        if not runner.exists():
            raise RuntimeError(f"r3PG runner script not found: {runner}")

        payload = request.model_dump()
        result = _run_r3pg_payload(payload, runner)

        outputs = [
            _normalize_annual_output(
                row,
                fallback_volume_m3_ha=input_volume,
                fallback_stems_per_ha=input_stems,
            )
            for row in result.get("annual_outputs", [])
        ]
        summary = result.get("summary", {})
        fallback_outputs = _run_missing_planted_cohorts(payload, outputs, runner)
        if fallback_outputs:
            outputs.extend(fallback_outputs)
            outputs.sort(key=lambda item: (item.year, item.species or ""))
            summary.setdefault("fallback_cohort_runs", [])
            for species_name in sorted({output.species for output in fallback_outputs if output.species}):
                summary["fallback_cohort_runs"].append(
                    {
                        "species": species_name,
                        "note": "Planted cohort was missing from the combined r3PG run and was rerun separately.",
                    }
                )
        summary.setdefault(
            "warning",
            "r3PG mixed-stand output normalization is provisional. Validate variable mappings before management use.",
        )
        if field_default_context:
            summary["field_defaults"] = field_default_context
        _add_sanity_warnings(summary, outputs)

        return SimulationResult(
            model_name=self.model_name,
            model_version=result.get("model_version"),
            adapter_key=self.adapter_key,
            output_frequency="monthly_raw_annual_normalized",
            input_parameters=payload,
            outputs=outputs,
            summary=summary,
        raw_outputs={"records": result.get("raw_records", [])},
    )


def _run_r3pg_payload(payload: dict[str, Any], runner: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="forestgpt_r3pg_") as tmp_dir:
        input_path = Path(tmp_dir) / "input.json"
        output_path = Path(tmp_dir) / "output.json"
        input_path.write_text(json.dumps(payload), encoding="utf-8")

        completed = subprocess.run(
            [RSCRIPT_BIN, str(runner), str(input_path), str(output_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "r3PG runner failed.\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            )
        return json.loads(output_path.read_text(encoding="utf-8"))


def _run_missing_planted_cohorts(
    payload: dict[str, Any],
    outputs: list[AnnualSimulationOutput],
    runner: Path,
) -> list[AnnualSimulationOutput]:
    raw_inputs = payload.get("raw_inputs") or {}
    species_rows = raw_inputs.get("species") or []
    output_species = {output.species for output in outputs}
    missing_rows = [
        row for row in species_rows
        if row.get("species") not in output_species and _is_future_planted_row(row, raw_inputs)
    ]
    fallback_outputs: list[AnnualSimulationOutput] = []
    for row in missing_rows:
        species_name = row.get("species")
        single_payload = {
            **payload,
            "raw_inputs": _single_species_raw_inputs(raw_inputs, species_name),
        }
        result = _run_r3pg_payload(single_payload, runner)
        planted_year = _year_from_planted(row.get("planted"))
        fallback_outputs.extend(
            _normalize_annual_output(item)
            for item in result.get("annual_outputs", [])
            if item.get("species") == species_name and int(item.get("year", 0)) >= planted_year
        )
    return fallback_outputs


def _single_species_raw_inputs(raw_inputs: dict[str, Any], species_name: str | None) -> dict[str, Any]:
    if not species_name:
        return raw_inputs
    raw_copy = dict(raw_inputs)
    raw_copy["species"] = [row for row in raw_inputs.get("species", []) if row.get("species") == species_name]
    raw_copy["parameters"] = _filter_parameter_rows(raw_inputs.get("parameters"), species_name)
    raw_copy["size_dist"] = _filter_parameter_rows(raw_inputs.get("size_dist"), species_name)
    raw_copy["thinning"] = [
        row for row in raw_inputs.get("thinning", [])
        if row.get("species") == species_name
    ]
    metadata = dict(raw_inputs.get("metadata") or {})
    metadata["dynamic_thinning"] = [
        row for row in metadata.get("dynamic_thinning", [])
        if row.get("species") == species_name
    ]
    raw_copy["metadata"] = metadata
    return raw_copy


def _filter_parameter_rows(rows: list[dict] | None, species_name: str) -> list[dict]:
    if not rows:
        return []
    return [
        {"parameter": row.get("parameter"), species_name: row.get(species_name)}
        for row in rows
    ]


def _is_future_planted_row(row: dict[str, Any], raw_inputs: dict[str, Any]) -> bool:
    planted_year = _year_from_planted(row.get("planted"))
    start_year = int((raw_inputs.get("metadata") or {}).get("start_year", 2026))
    return planted_year > start_year


def _year_from_planted(value: Any) -> int:
    if value is None:
        return 0
    return int(str(value)[:4])

def _normalize_annual_output(
    row: dict[str, Any],
    fallback_volume_m3_ha: float | dict[str, float] | None = None,
    fallback_stems_per_ha: float | dict[str, float] | None = None,
) -> AnnualSimulationOutput:
    volume = _optional_float(row.get("standing_volume_m3_ha"))
    mai = _optional_float(row.get("mean_annual_increment_m3_ha_yr"))
    stems = _optional_float(row.get("stems_per_ha"))
    notes = list(row.get("notes") or [])
    species = row.get("species")
    fallback_volume = _fallback_for_species(fallback_volume_m3_ha, species)
    fallback_stems = _fallback_for_species(fallback_stems_per_ha, species)
    if fallback_volume is not None and (volume is None or volume > 2000):
        volume = fallback_volume
        notes.append("Standing volume replaced with input-derived estimate after r3PG sanity check failed.")
    if stems is None and fallback_stems is not None:
        stems = fallback_stems
        notes.append("Stem number taken from completed input because r3PG did not return a value.")
    if mai is not None and mai > 100:
        notes.append("MAI omitted because normalized r3PG value failed sanity check.")
        mai = None

    return AnnualSimulationOutput(
        year=int(row.get("year", 0)),
        species=species,
        age_years=int(row.get("age_years", row.get("year", 0))),
        stems_per_ha=stems,
        basal_area_m2_ha=float(row.get("basal_area_m2_ha") or 0),
        mean_dbh_cm=_optional_float(row.get("mean_dbh_cm")),
        mean_height_m=_optional_float(row.get("mean_height_m")),
        standing_volume_m3_ha=volume,
        aboveground_biomass_t_ha=float(row.get("aboveground_biomass_t_ha") or 0),
        mean_annual_increment_m3_ha_yr=mai,
        canopy_cover=_optional_float(row.get("canopy_cover")),
        canopy_cover_max=_optional_float(row.get("canopy_cover_max")),
        canopy_volume_fraction=_optional_float(row.get("canopy_volume_fraction")),
        canopy_volume_fraction_max=_optional_float(row.get("canopy_volume_fraction_max")),
        notes=notes,
    )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _fallback_for_species(value: float | dict[str, float] | None, species: Any) -> float | None:
    if value is None or isinstance(value, (int, float)):
        return value
    normalized_species = _normalize_species(species)
    if normalized_species in value:
        return value[normalized_species]
    return value.get(str(species))


def _normalize_species(value: Any) -> str | None:
    if value is None:
        return None
    aliases = {
        "beech": "Fagus sylvatica",
        "buche": "Fagus sylvatica",
        "european beech": "Fagus sylvatica",
        "fagus sylvatica": "Fagus sylvatica",
        "douglas fir": "Pseudotsuga menziesii",
        "douglasie": "Pseudotsuga menziesii",
        "pseudotsuga menziesii": "Pseudotsuga menziesii",
        "fir": "Abies alba",
        "silver fir": "Abies alba",
        "tanne": "Abies alba",
        "abies alba": "Abies alba",
        "larch": "Larix decidua",
        "laerche": "Larix decidua",
        "lärche": "Larix decidua",
        "larix decidua": "Larix decidua",
        "oak": "Quercus robur",
        "eiche": "Quercus robur",
        "quercus robur": "Quercus robur",
        "pine": "Pinus sylvestris",
        "scots pine": "Pinus sylvestris",
        "kiefer": "Pinus sylvestris",
        "pinus sylvestris": "Pinus sylvestris",
        "spruce": "Picea abies",
        "norway spruce": "Picea abies",
        "picea abies": "Picea abies",
    }
    return aliases.get(str(value).lower(), str(value))


def _add_sanity_warnings(summary: dict[str, Any], outputs: list[AnnualSimulationOutput]) -> None:
    warnings = summary.setdefault("sanity_warnings", [])
    if any(
        "Standing volume replaced with input-derived estimate" in note
        for output in outputs
        for note in output.notes
    ):
        warnings.append(
            "One or more r3PG standing-volume values failed sanity checks and were replaced by the completed input-derived estimate."
        )
    if any(output.basal_area_m2_ha > 100 for output in outputs):
        warnings.append("Basal area exceeds 100 m2/ha. Check stand inputs and parameter set.")
