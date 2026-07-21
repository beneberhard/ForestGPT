from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SimulatorCapability(BaseModel):
    name: str
    version: str | None = None
    description: str
    input_modes: list[str] = Field(default_factory=list)
    output_frequency: str
    supports_mixtures: bool = False
    supports_thinning: bool = False
    requires_external_runtime: str | None = None


class GrowthSimulationRequest(BaseModel):
    stand_id: int | None = None
    simulator: str | None = Field(None, description="Optional adapter key. Currently supported: r3pg.")
    input_mode: str = Field(
        "simplified",
        description="simplified uses app-level fields; r3pg_tables passes raw r3PG input tables.",
    )
    parameters: dict[str, Any] = Field(default_factory=dict)
    raw_inputs: dict[str, Any] = Field(
        default_factory=dict,
        description="Adapter-specific inputs such as r3PG site/species/climate/thinning/parameters tables.",
    )
    field_input: dict[str, Any] = Field(
        default_factory=dict,
        description="Forester-friendly stand input; missing values are filled by the default engine.",
    )


class DefaultAssumption(BaseModel):
    field: str
    value: Any
    reason: str
    confidence: str = "medium"


class FieldDefaultPreview(BaseModel):
    completed_parameters: dict[str, Any]
    assumptions: list[DefaultAssumption]
    warnings: list[str] = Field(default_factory=list)
    r3pg_tables: dict[str, Any] | None = None


class SimulationInput(BaseModel):
    stand_id: int
    species: str = Field(..., examples=["European beech"])
    initial_age_years: int = Field(..., ge=0)
    horizon_years: int = Field(20, ge=1, le=100)
    area_ha: float | None = Field(None, gt=0)
    initial_stems_per_ha: float | None = Field(None, gt=0)
    initial_basal_area_m2_ha: float | None = Field(None, gt=0)
    site_fertility: float = Field(0.7, ge=0, le=1)
    soil_water_capacity_mm: float | None = Field(None, gt=0)
    thinning_schedule: list[dict[str, Any]] = Field(default_factory=list)
    climate: dict[str, Any] = Field(default_factory=dict)
    extra_parameters: dict[str, Any] = Field(default_factory=dict)


class AnnualSimulationOutput(BaseModel):
    year: int
    species: str | None = None
    age_years: int
    stems_per_ha: float | None = None
    basal_area_m2_ha: float
    mean_dbh_cm: float | None = None
    mean_height_m: float | None = None
    standing_volume_m3_ha: float | None = None
    aboveground_biomass_t_ha: float
    mean_annual_increment_m3_ha_yr: float | None = None
    canopy_cover: float | None = None
    canopy_cover_max: float | None = None
    canopy_volume_fraction: float | None = None
    canopy_volume_fraction_max: float | None = None
    notes: list[str] = Field(default_factory=list)


class SimulationResult(BaseModel):
    model_name: str
    model_version: str | None = None
    adapter_key: str = "r3pg"
    output_frequency: str = "annual"
    input_parameters: dict[str, Any]
    outputs: list[AnnualSimulationOutput]
    summary: dict[str, Any]
    raw_outputs: dict[str, Any] | None = None


class SimulationRunCreate(BaseModel):
    stand_id: int
    parameters: SimulationInput


class SimulationOutputRead(BaseModel):
    year: int
    output: dict[str, Any]

    model_config = {"from_attributes": True}


class SimulationRunRead(BaseModel):
    id: int
    stand_id: int | None = None
    model_name: str
    model_version: str | None = None
    input_parameters: dict[str, Any]
    summary: dict[str, Any] | None = None
    status: str
    created_at: datetime
    completed_at: datetime | None = None
    outputs: list[SimulationOutputRead] = Field(default_factory=list)

    model_config = {"from_attributes": True}
