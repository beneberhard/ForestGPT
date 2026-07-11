from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class StandCreate(BaseModel):
    id: int | None = Field(None, ge=1)
    name: str
    species: str | None = None
    area_ha: float | None = Field(None, gt=0)
    age_years: int | None = Field(None, ge=0)
    geometry_wkt: str | None = Field(
        None,
        description="Optional WKT polygon in EPSG:4326. GeoJSON support can be added next.",
    )
    properties: dict[str, Any] | None = None


class StandUpdate(BaseModel):
    name: str | None = None
    species: str | None = None
    area_ha: float | None = Field(None, gt=0)
    age_years: int | None = Field(None, ge=0)
    geometry_wkt: str | None = Field(
        None,
        description="Optional WKT polygon in EPSG:4326.",
    )
    properties: dict[str, Any] | None = None


class StandGeometryLink(BaseModel):
    source_table: str = Field(..., description="PostGIS table containing the uploaded geometry.")
    source_id: int | str = Field(..., description="Feature id in the source table.")
    source_id_column: str = "id"
    geometry_column: str = "geom"
    source_schema: str = "public"


class StandRead(BaseModel):
    id: int
    name: str
    species: str | None = None
    area_ha: float | None = None
    age_years: int | None = None
    properties: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class StandObservationCreate(BaseModel):
    observed_at: datetime | None = None
    observer: str | None = None
    category: str | None = None
    note: str = Field(..., min_length=1)
    properties: dict[str, Any] | None = None


class StandObservationRead(BaseModel):
    id: int
    stand_id: int
    observed_at: datetime
    observer: str | None = None
    category: str | None = None
    note: str
    properties: dict[str, Any] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
