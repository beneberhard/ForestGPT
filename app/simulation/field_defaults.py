from functools import lru_cache
from math import pi
from pathlib import Path
from typing import Any

import pandas as pd

from app.simulation.schemas import DefaultAssumption, FieldDefaultPreview, GrowthSimulationRequest


YIELD_TABLES = {
    "buche_braunschweig": Path("data/yield_table_forestgpt_buche_braunschweig.xlsx"),
    "douglasie_baden": Path("data/yield_table_forestgpt_douglasie_baden.xlsx"),
    "fichte_bayern": Path("data/yield_table_forestgpt_fichte_bayern.xlsx"),
    "kiefer_litschau": Path("data/yield_table_forestgpt_kiefer_litschau.xlsx"),
    "laerche_schweiz": Path("data/yield_table_forestgpt_laerche_schweiz.xlsx"),
    "tanne_wuerttemberg": Path("data/yield_table_forestgpt_tanne_wuerttemberg.xlsx"),
    "eiche_ungarn": Path("data/yield_table_forestgpt_eiche_ungarn.xlsx"),
}
SPECIES_ALIASES = {
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
    "norway spruce": "Picea abies",
    "spruce": "Picea abies",
    "fichte": "Picea abies",
    "picea abies": "Picea abies",
}
DEFAULT_YIELD_TABLE_BY_SPECIES = {
    "Fagus sylvatica": "buche_braunschweig",
    "Pseudotsuga menziesii": "douglasie_baden",
    "Abies alba": "tanne_wuerttemberg",
    "Larix decidua": "laerche_schweiz",
    "Quercus robur": "eiche_ungarn",
    "Pinus sylvestris": "kiefer_litschau",
    "Picea abies": "fichte_bayern",
}


def complete_field_input(request: GrowthSimulationRequest) -> FieldDefaultPreview:
    raw = request.field_input or request.parameters
    assumptions: list[DefaultAssumption] = []
    warnings: list[str] = []

    species_entries = raw.get("species_entries")
    if species_entries:
        completed_entries = []
        active_species_count = len(species_entries)
        for index, entry in enumerate(species_entries, start=1):
            species_completed, species_assumptions, species_warnings = _complete_species_input(
                entry,
                raw,
                index,
                active_species_count,
            )
            completed_entries.append(species_completed)
            assumptions.extend(species_assumptions)
            warnings.extend(species_warnings)

        completed = {
            "species_entries": completed_entries,
            "horizon_years": _take_shared(raw, assumptions, "horizon_years", 20, "Default planning horizon."),
            "site_fertility": _take_shared(
                raw,
                assumptions,
                "site_fertility",
                0.65,
                "Default medium site fertility for first prototype.",
            ),
            "soil_water_capacity_mm": _soil_water_capacity(raw, assumptions),
            "latitude": raw.get("latitude"),
            "altitude": raw.get("altitude"),
            "slope": raw.get("slope"),
            "aspect": raw.get("aspect"),
            "soil_type": raw.get("soil_type"),
            "thinning_schedule": raw.get("thinning_schedule", []),
        }
        completed = {key: value for key, value in completed.items() if value is not None}
        if "latitude" not in completed:
            warnings.append("Location missing: example r3PG climate/site location is used.")
        return FieldDefaultPreview(completed_parameters=completed, assumptions=assumptions, warnings=warnings)

    def take(name: str, default: Any, reason: str, confidence: str = "medium") -> Any:
        value = raw.get(name)
        if value is None:
            assumptions.append(DefaultAssumption(field=name, value=default, reason=reason, confidence=confidence))
            return default
        return value

    raw_species = take("species", "Picea abies", "Starting species default.")
    species = SPECIES_ALIASES.get(str(raw_species).lower(), raw_species)
    planted_year = _planted_year(raw.get("planted_year", raw.get("planted")))
    age = raw.get("age_years", raw.get("initial_age_years"))
    if age is None and planted_year is not None:
        start_year = int(raw.get("start_year", 2026))
        age = start_year - planted_year
        assumptions.append(
            DefaultAssumption(
                field="age_years",
                value=age,
                reason=f"Derived from planted_year={planted_year} and start_year={start_year}.",
            )
        )
    start_year = int(raw.get("start_year", 2026))
    is_planting_cohort = planted_year is not None and int(age) <= 0
    if age is None:
        age = 40
        assumptions.append(DefaultAssumption(field="age_years", value=age, reason="Default stand age for first prototype."))
    yield_estimate = None
    used_yield_table_id = None
    has_inventory_structure = all(
        value is not None
        for value in (
            raw.get("stems_per_ha", raw.get("initial_stems_per_ha")),
            raw.get("mean_dbh_cm", raw.get("dbh_cm")),
            raw.get("mean_height_m", raw.get("height_m")),
        )
    )
    if age is not None and raw.get("top_height_m") is not None and not has_inventory_structure and not is_planting_cohort:
        yield_table_id = raw.get("yield_table_id", "fichte_bayern")
        used_yield_table_id = yield_table_id
        if raw.get("yield_table_id") is None:
            assumptions.append(
                DefaultAssumption(
                    field="yield_table_id",
                    value=yield_table_id,
                    reason="Default yield table for Norway spruce prototype.",
                )
            )
        try:
            yield_estimate = YieldTableEstimator().estimate_from_age_top_height(
                species=species,
                age=int(age),
                top_height_m=float(raw["top_height_m"]),
                yield_table_id=yield_table_id,
            )
        except ValueError as exc:
            raise ValueError(f"Yield-table estimation failed: {exc}") from exc
        if yield_estimate.get("warning"):
            warnings.append(yield_estimate["warning"])

    stems = raw.get("stems_per_ha", raw.get("initial_stems_per_ha"))
    if stems is None and yield_estimate:
        stems = round(yield_estimate["stems_ha"])
        assumptions.append(_yield_assumption("stems_ha", stems, yield_estimate))
    if stems is None:
        stems = 1600 if is_planting_cohort else 800
        assumptions.append(
            DefaultAssumption(
                field="stems_per_ha",
                value=stems,
                reason="Default planting density." if is_planting_cohort else "Default Norway spruce stocking.",
            )
        )
    soil_moisture = str(take("soil_moisture", "mesic", "Default medium soil moisture class.")).lower()

    soil_water_by_moisture = {"dry": 80, "mesic": 120, "moist": 160, "wet": 200}
    soil_water = raw.get("soil_water_capacity_mm")
    if soil_water is None:
        soil_water = soil_water_by_moisture.get(soil_moisture, 120)
        assumptions.append(
            DefaultAssumption(
                field="soil_water_capacity_mm",
                value=soil_water,
                reason=f"Mapped from soil_moisture='{soil_moisture}'.",
            )
        )

    dbh = raw.get("mean_dbh_cm", raw.get("dbh_cm"))
    if dbh is None and yield_estimate:
        dbh = round(yield_estimate["mean_dbh_cm"], 1)
        assumptions.append(_yield_assumption("mean_dbh_cm", dbh, yield_estimate))

    height = raw.get("mean_height_m", raw.get("height_m"))
    if height is None and yield_estimate:
        height = round(yield_estimate["mean_height_m"], 1)
        assumptions.append(_yield_assumption("mean_height_m", height, yield_estimate))

    volume = raw.get("volume_m3_ha")
    if volume is None and yield_estimate:
        volume = round(yield_estimate["volume_m3_ha"], 1)
        assumptions.append(_yield_assumption("volume_m3_ha", volume, yield_estimate))
    if volume is None and all(value is not None for value in (stems, dbh, height)):
        form_factor = 0.45 if species == "Picea abies" else 0.49
        volume = round(pi * (float(dbh) / 100 / 2) ** 2 * float(height) * float(stems) * form_factor, 1)
        assumptions.append(
            DefaultAssumption(
                field="volume_m3_ha",
                value=volume,
                reason="Derived from supplied stem number, mean DBH, and mean height using a species form factor.",
                confidence="medium",
            )
        )

    stem_biomass = raw.get("initial_stem_biomass_t_ha")
    root_biomass = raw.get("initial_root_biomass_t_ha")
    foliage_biomass = raw.get("initial_foliage_biomass_t_ha")
    if is_planting_cohort and any(value is None for value in (stem_biomass, root_biomass, foliage_biomass)):
        planting_biomass = _planting_biomass_defaults(float(stems))
        if stem_biomass is None:
            stem_biomass = planting_biomass["stem"]
            assumptions.append(_planting_biomass_assumption("initial_stem_biomass_t_ha", stem_biomass))
        if root_biomass is None:
            root_biomass = planting_biomass["root"]
            assumptions.append(_planting_biomass_assumption("initial_root_biomass_t_ha", root_biomass))
        if foliage_biomass is None:
            foliage_biomass = planting_biomass["foliage"]
            assumptions.append(_planting_biomass_assumption("initial_foliage_biomass_t_ha", foliage_biomass))
    elif stem_biomass is None and species == "Picea abies" and dbh is not None and stems is not None:
        stem_biomass = round(0.133 * float(dbh) ** 2.305 * float(stems) / 1000, 2)
        assumptions.append(
            DefaultAssumption(
                field="initial_stem_biomass_t_ha",
                value=stem_biomass,
                reason="Estimated from DBH and stems/ha using the selected r3PG Norway spruce aWS/nWS allometry.",
                confidence="medium",
            )
        )
    elif stem_biomass is None and volume is not None:
        stem_biomass = round(float(volume) * 0.4, 2)
        assumptions.append(
            DefaultAssumption(
                field="initial_stem_biomass_t_ha",
                value=stem_biomass,
                reason="Estimated from volume_m3_ha using wood density 0.4 Mg/m3.",
                confidence="low",
            )
        )

    completed = {
        "species": species,
        "planted_year": planted_year,
        "initial_age_years": age,
        "horizon_years": take("horizon_years", 20, "Default planning horizon."),
        "initial_stems_per_ha": stems,
        "site_fertility": take("site_fertility", 0.65, "Default medium site fertility for first prototype."),
        "soil_water_capacity_mm": soil_water,
        "latitude": raw.get("latitude"),
        "altitude": raw.get("altitude"),
        "slope": raw.get("slope"),
        "aspect": raw.get("aspect"),
        "soil_type": raw.get("soil_type"),
        "top_height_m": raw.get("top_height_m"),
        "yield_table_id": used_yield_table_id,
        "site_class_estimated": yield_estimate.get("site_class_estimated") if yield_estimate else None,
        "dbh_cm": dbh,
        "height_m": height,
        "volume_m3_ha": volume,
        "initial_stem_biomass_t_ha": stem_biomass,
        "initial_root_biomass_t_ha": root_biomass if root_biomass is not None else round(stem_biomass * 0.25, 2) if stem_biomass else None,
        "initial_foliage_biomass_t_ha": foliage_biomass if foliage_biomass is not None else round(stem_biomass * 0.03, 2) if stem_biomass else None,
        "thinning_schedule": raw.get("thinning_schedule", []),
    }
    completed = {key: value for key, value in completed.items() if value is not None}

    if "dbh_cm" not in completed:
        warnings.append("DBH missing: biomass remains estimated from default r3PG species table values.")
    if "height_m" not in completed:
        warnings.append("Height missing: r3PG height develops from selected parameter set.")
    if "latitude" not in completed:
        warnings.append("Location missing: example r3PG climate/site location is used.")

    return FieldDefaultPreview(completed_parameters=completed, assumptions=assumptions, warnings=warnings)


def _take_shared(
    raw: dict[str, Any],
    assumptions: list[DefaultAssumption],
    name: str,
    default: Any,
    reason: str,
    confidence: str = "medium",
) -> Any:
    value = raw.get(name)
    if value is None:
        assumptions.append(DefaultAssumption(field=name, value=default, reason=reason, confidence=confidence))
        return default
    return value


def _soil_water_capacity(raw: dict[str, Any], assumptions: list[DefaultAssumption]) -> Any:
    soil_moisture = raw.get("soil_moisture")
    if soil_moisture is None:
        soil_moisture = "mesic"
        assumptions.append(
            DefaultAssumption(field="soil_moisture", value=soil_moisture, reason="Default medium soil moisture class.")
        )
    soil_water_by_moisture = {"dry": 80, "mesic": 120, "moist": 160, "wet": 200}
    soil_water = raw.get("soil_water_capacity_mm")
    if soil_water is None:
        soil_water = soil_water_by_moisture.get(str(soil_moisture).lower(), 120)
        assumptions.append(
            DefaultAssumption(
                field="soil_water_capacity_mm",
                value=soil_water,
                reason=f"Mapped from soil_moisture='{str(soil_moisture).lower()}'.",
            )
        )
    return soil_water


def _planted_year(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    return int(text[:4])


def _planting_biomass_defaults(stems_per_ha: float) -> dict[str, float]:
    scale = stems_per_ha / 1000
    return {
        "stem": round(0.05 * scale, 4),
        "root": round(0.025 * scale, 4),
        "foliage": round(0.02 * scale, 4),
    }


def _planting_biomass_assumption(field: str, value: float) -> DefaultAssumption:
    return DefaultAssumption(
        field=field,
        value=value,
        reason=(
            "Default seedling biomass for explicitly planted cohorts. "
            "Assumes 0.05 t/ha stem, 0.025 t/ha root, and 0.02 t/ha foliage per 1000 planted trees/ha."
        ),
        confidence="low",
    )


def _complete_species_input(
    entry: dict[str, Any],
    shared: dict[str, Any],
    index: int,
    active_species_count: int = 1,
) -> tuple[dict[str, Any], list[DefaultAssumption], list[str]]:
    assumptions: list[DefaultAssumption] = []
    warnings: list[str] = []

    raw_species = entry.get("species") or entry.get("species_name")
    if not raw_species:
        raw_species = ["Norway spruce", "larch", "beech"][min(index - 1, 2)]
        assumptions.append(
            DefaultAssumption(
                field=f"species_entries[{index}].species",
                value=raw_species,
                reason="Default species row in development dashboard.",
            )
        )
    species = SPECIES_ALIASES.get(str(raw_species).lower(), raw_species)

    planted_year = _planted_year(entry.get("planted_year", entry.get("planted")))
    age = entry.get("age_years", entry.get("initial_age_years"))
    start_year = int(shared.get("start_year", 2026))
    if age is None and planted_year is not None:
        age = start_year - planted_year
        assumptions.append(
            DefaultAssumption(
                field=f"{species}.age_years",
                value=age,
                reason=f"Derived from planted_year={planted_year} and start_year={start_year}.",
            )
        )
    if age is None:
        raise ValueError(f"Species row {index} requires age_years.")
    is_planting_cohort = planted_year is not None and int(age) <= 0

    stems = entry.get("stems_per_ha", entry.get("initial_stems_per_ha"))
    dbh = entry.get("mean_dbh_cm", entry.get("dbh_cm"))
    height = entry.get("mean_height_m", entry.get("height_m"))
    has_inventory_structure = all(value is not None for value in (stems, dbh, height))

    yield_estimate = None
    used_yield_table_id = None
    stocking_degree = _stocking_degree(entry)
    species_share = _species_share(entry, active_species_count)
    yield_scale = stocking_degree * species_share
    if entry.get("top_height_m") is not None and not has_inventory_structure and not is_planting_cohort:
        yield_table_id = entry.get("yield_table_id") or DEFAULT_YIELD_TABLE_BY_SPECIES.get(str(species), "fichte_bayern")
        used_yield_table_id = yield_table_id
        if entry.get("yield_table_id") is None:
            assumptions.append(
                DefaultAssumption(
                    field=f"{species}.yield_table_id",
                    value=yield_table_id,
                    reason="Default yield table for species.",
                )
            )
        yield_estimate = YieldTableEstimator().estimate_from_age_top_height(
            species=str(species),
            age=int(age),
            top_height_m=float(entry["top_height_m"]),
            yield_table_id=yield_table_id,
        )
        if yield_estimate.get("warning"):
            warnings.append(f"{species}: {yield_estimate['warning']}")

    if stems is None and yield_estimate:
        stems = round(yield_estimate["stems_ha"] * yield_scale)
        assumptions.append(_yield_assumption(f"{species}.stems_ha", stems, yield_estimate))
        _append_scaling_assumptions(species, assumptions, stocking_degree, species_share, yield_scale)
    if stems is None and is_planting_cohort:
        stems = 1600
        assumptions.append(
            DefaultAssumption(
                field=f"{species}.stems_ha",
                value=stems,
                reason="Default planting density.",
            )
        )
    if dbh is None and yield_estimate:
        dbh = round(yield_estimate["mean_dbh_cm"], 1)
        assumptions.append(_yield_assumption(f"{species}.mean_dbh_cm", dbh, yield_estimate))
    if height is None and yield_estimate:
        height = round(yield_estimate["mean_height_m"], 1)
        assumptions.append(_yield_assumption(f"{species}.mean_height_m", height, yield_estimate))

    if not is_planting_cohort and (stems is None or dbh is None or height is None):
        raise ValueError(
            f"{species} requires either stems/ha, mean DBH, and mean height; or age plus top height for yield-table estimation."
        )

    volume = entry.get("volume_m3_ha")
    if volume is None and yield_estimate:
        volume = round(yield_estimate["volume_m3_ha"] * yield_scale, 1)
        assumptions.append(_yield_assumption(f"{species}.volume_m3_ha", volume, yield_estimate))
    if volume is None and not is_planting_cohort:
        form_factor = 0.49 if species == "Fagus sylvatica" else 0.45
        volume = round(pi * (float(dbh) / 100 / 2) ** 2 * float(height) * float(stems) * form_factor, 1)
        assumptions.append(
            DefaultAssumption(
                field=f"{species}.volume_m3_ha",
                value=volume,
                reason="Derived from supplied stem number, mean DBH, and mean height using a species form factor.",
                confidence="medium",
            )
        )

    stem_biomass = entry.get("initial_stem_biomass_t_ha")
    root_biomass = entry.get("initial_root_biomass_t_ha")
    foliage_biomass = entry.get("initial_foliage_biomass_t_ha")
    if is_planting_cohort and any(value is None for value in (stem_biomass, root_biomass, foliage_biomass)):
        planting_biomass = _planting_biomass_defaults(float(stems))
        if stem_biomass is None:
            stem_biomass = planting_biomass["stem"]
            assumptions.append(_planting_biomass_assumption(f"{species}.initial_stem_biomass_t_ha", stem_biomass))
        if root_biomass is None:
            root_biomass = planting_biomass["root"]
            assumptions.append(_planting_biomass_assumption(f"{species}.initial_root_biomass_t_ha", root_biomass))
        if foliage_biomass is None:
            foliage_biomass = planting_biomass["foliage"]
            assumptions.append(_planting_biomass_assumption(f"{species}.initial_foliage_biomass_t_ha", foliage_biomass))
    elif stem_biomass is None and species == "Picea abies":
        stem_biomass = round(0.133 * float(dbh) ** 2.305 * float(stems) / 1000, 2)
        assumptions.append(
            DefaultAssumption(
                field=f"{species}.initial_stem_biomass_t_ha",
                value=stem_biomass,
                reason="Estimated from DBH and stems/ha using the selected r3PG Norway spruce aWS/nWS allometry.",
                confidence="medium",
            )
        )
    elif stem_biomass is None:
        density = 0.49 if species == "Fagus sylvatica" else 0.45
        stem_biomass = round(float(volume) * density, 2)
        assumptions.append(
            DefaultAssumption(
                field=f"{species}.initial_stem_biomass_t_ha",
                value=stem_biomass,
                reason="Estimated from volume_m3_ha using a provisional wood density.",
                confidence="low",
            )
        )

    completed = {
        "species": species,
        "cohort_label": entry.get("cohort_label", entry.get("cohort_id")),
        "planted_year": planted_year,
        "initial_age_years": age,
        "initial_stems_per_ha": stems,
        "dbh_cm": dbh,
        "height_m": height,
            "top_height_m": entry.get("top_height_m"),
            "yield_table_id": used_yield_table_id,
            "stocking_degree": stocking_degree if stocking_degree != 1 else entry.get("stocking_degree"),
            "mixture_share": species_share if species_share < 1 else entry.get("mixture_share"),
            "yield_table_scale": yield_scale if yield_scale != 1 else None,
            "site_class_estimated": yield_estimate.get("site_class_estimated") if yield_estimate else None,
        "volume_m3_ha": volume,
        "initial_stem_biomass_t_ha": stem_biomass,
        "initial_root_biomass_t_ha": root_biomass if root_biomass is not None else round(stem_biomass * 0.25, 2) if stem_biomass else None,
        "initial_foliage_biomass_t_ha": foliage_biomass if foliage_biomass is not None else round(stem_biomass * 0.03, 2) if stem_biomass else None,
    }
    return (
        {key: value for key, value in completed.items() if value is not None},
        assumptions,
        warnings,
    )


def _species_share(entry: dict[str, Any], active_species_count: int) -> float:
    raw_share = entry.get("mixture_share", entry.get("share", entry.get("share_percent")))
    if raw_share is not None:
        share = float(raw_share)
        return share / 100 if share > 1 else share
    return 1 / active_species_count if active_species_count > 1 else 1.0


def _stocking_degree(entry: dict[str, Any]) -> float:
    value = entry.get("stocking_degree")
    return 1.0 if value is None else float(value)


def _append_scaling_assumptions(
    species: str,
    assumptions: list[DefaultAssumption],
    stocking_degree: float,
    species_share: float,
    yield_scale: float,
) -> None:
    if stocking_degree != 1:
        assumptions.append(
            DefaultAssumption(
                field=f"{species}.stocking_degree",
                value=round(stocking_degree, 3),
                reason="Pure-stand yield-table values were scaled by stocking degree.",
                confidence="medium",
            )
        )
    if species_share != 1:
        assumptions.append(
            DefaultAssumption(
                field=f"{species}.mixture_share",
                value=round(species_share, 3),
                reason="Pure-stand yield-table values were scaled by species share.",
                confidence="medium",
            )
        )
    if yield_scale != 1:
        assumptions.append(
            DefaultAssumption(
                field=f"{species}.yield_table_scale",
                value=round(yield_scale, 3),
                reason="Final scaling factor applied to yield-table stem number and volume.",
                confidence="medium",
            )
        )


class YieldTableEstimator:
    def estimate_from_age_top_height(
        self,
        species: str,
        age: int,
        top_height_m: float,
        yield_table_id: str,
    ) -> dict[str, Any]:
        table = _load_yield_table(yield_table_id)
        rounded_age = int(round(age / 5) * 5)
        rows = table[table["age"] == rounded_age].sort_values("top_height_m")
        if rows.empty:
            raise ValueError(f"No yield-table rows for rounded age {rounded_age}.")

        low = rows[rows["top_height_m"] <= top_height_m].tail(1)
        high = rows[rows["top_height_m"] >= top_height_m].head(1)
        outside_range = low.empty or high.empty
        if low.empty:
            low = rows.head(1)
        if high.empty:
            high = rows.tail(1)
        if outside_range:
            low = high = low if top_height_m < float(rows["top_height_m"].min()) else high

        low_row = low.iloc[0]
        high_row = high.iloc[0]
        low_height = float(low_row["top_height_m"])
        high_height = float(high_row["top_height_m"])
        ratio = 0.0 if high_height == low_height else (top_height_m - low_height) / (high_height - low_height)
        site_class_calc = float(low_row["site_class"]) + ratio
        resulting_stems_ha = int(
            float(low_row["stems_ha"])
            + (float(high_row["stems_ha"]) - float(low_row["stems_ha"])) * ratio
        )
        resulting_dbh = int(
            float(low_row["mean_dbh_cm"])
            + (float(high_row["mean_dbh_cm"]) - float(low_row["mean_dbh_cm"])) * ratio
        )
        resulting_mean_height = int(
            float(low_row["mean_height_m"])
            + (float(high_row["mean_height_m"]) - float(low_row["mean_height_m"])) * ratio
        )
        if "stem_volume_ha_in_m3" in rows.columns:
            resulting_volume = int(
                float(low_row["stem_volume_ha_in_m3"])
                + (
                    float(high_row["stem_volume_ha_in_m3"])
                    - float(low_row["stem_volume_ha_in_m3"])
                )
                * ratio
            )
        else:
            form_factor = 0.45 if species == "Picea abies" else 0.49
            resulting_volume = int(
                (resulting_dbh / 100 / 2) ** 2
                * pi
                * resulting_mean_height
                * resulting_stems_ha
                * form_factor
            )

        return {
            "age": rounded_age,
            "top_height_m": top_height_m,
            "site_class_estimated": site_class_calc,
            "stems_ha": resulting_stems_ha,
            "mean_dbh_cm": resulting_dbh,
            "mean_height_m": resulting_mean_height,
            "volume_m3_ha": resulting_volume,
            "source": f"yield_table:{yield_table_id}",
            "method": (
                "nearest available site class"
                if outside_range
                else "linear interpolation between neighbouring site classes"
            ),
            "confidence": "low" if outside_range else "medium",
            "warning": (
                f"top_height_m={top_height_m} is outside the yield-table range "
                f"{float(rows['top_height_m'].min())}-{float(rows['top_height_m'].max())} "
                f"for age {rounded_age}; the nearest site class was used."
                if outside_range
                else None
            ),
        }


def _yield_assumption(field: str, value: Any, estimate: dict[str, Any]) -> DefaultAssumption:
    return DefaultAssumption(
        field=field,
        value=value,
        reason=f"{estimate['method']} from {estimate['source']} at rounded age {estimate['age']}.",
        confidence=estimate["confidence"],
    )


@lru_cache(maxsize=8)
def _load_yield_table(yield_table_id: str) -> pd.DataFrame:
    path = YIELD_TABLES.get(yield_table_id)
    if path is None:
        raise ValueError(f"Unknown yield_table_id: {yield_table_id}")
    table = pd.read_excel(path)
    return table.rename(
        columns={
            "bonitaet": "site_class",
            "alter": "age",
            "OH": "top_height_m",
            "MH": "mean_height_m",
            "BHD": "mean_dbh_cm",
            "formzahl": "form_factor",
            "N": "stems_ha",
            "G": "basal_area_ha_in_m2",
            "Vol": "stem_volume_ha_in_m3",
            "GWL": "total_volume",
        }
    )
