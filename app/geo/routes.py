import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from geoalchemy2 import WKTElement
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.geo.db import get_db
from app.geo.models import Stand, StandObservation
from app.geo.schemas import (
    StandCreate,
    StandGeometryLink,
    StandObservationCreate,
    StandObservationRead,
    StandRead,
    StandUpdate,
)
from app.spatial.terrain import terrain_summary_for_stand

router = APIRouter(prefix="/stands", tags=["stands"])


@router.post("", response_model=StandRead)
def create_stand(payload: StandCreate, db: Session = Depends(get_db)) -> Stand:
    if payload.id is not None and db.get(Stand, payload.id) is not None:
        raise HTTPException(status_code=409, detail=f"Stand ID {payload.id} already exists")
    geometry = WKTElement(payload.geometry_wkt, srid=4326) if payload.geometry_wkt else None
    stand = Stand(
        id=payload.id,
        name=payload.name,
        species=payload.species,
        area_ha=payload.area_ha,
        age_years=payload.age_years,
        geometry=geometry,
        properties=payload.properties,
    )
    db.add(stand)
    db.commit()
    db.refresh(stand)
    return stand


@router.get("", response_model=list[StandRead])
def list_stands(db: Session = Depends(get_db)) -> list[Stand]:
    return db.query(Stand).order_by(Stand.created_at.desc()).all()


@router.get("/geojson")
def list_stands_geojson(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.execute(
        text(
            """
            SELECT
                id,
                name,
                species,
                area_ha,
                age_years,
                properties,
                ST_AsGeoJSON(geometry)::json AS geometry
            FROM stands
            WHERE geometry IS NOT NULL
            ORDER BY created_at DESC
            """
        )
    ).mappings()
    features = []
    for row in rows:
        geometry = row["geometry"]
        if isinstance(geometry, str):
            geometry = json.loads(geometry)
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "id": row["id"],
                    "name": row["name"],
                    "species": row["species"],
                    "area_ha": row["area_ha"],
                    "age_years": row["age_years"],
                    "properties": row["properties"] or {},
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


@router.get("/{stand_id}/spatial-summary")
def get_stand_spatial_summary(stand_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    stand = db.get(Stand, stand_id)
    if stand is None:
        raise HTTPException(status_code=404, detail="Stand not found")

    geometry = _stand_geometry_summary(db, stand_id)
    return {
        "id": stand.id,
        "name": stand.name,
        "species": stand.species,
        "age_years": stand.age_years,
        "area_ha": stand.area_ha,
        "properties": stand.properties,
        "geometry": geometry,
        "terrain": terrain_summary_for_stand(db, stand_id),
    }


@router.get("/{stand_id}/observations", response_model=list[StandObservationRead])
def list_stand_observations(stand_id: int, db: Session = Depends(get_db)) -> list[StandObservation]:
    if db.get(Stand, stand_id) is None:
        raise HTTPException(status_code=404, detail="Stand not found")
    return (
        db.query(StandObservation)
        .filter(StandObservation.stand_id == stand_id)
        .order_by(StandObservation.observed_at.desc(), StandObservation.id.desc())
        .all()
    )


@router.post("/{stand_id}/observations", response_model=StandObservationRead)
def create_stand_observation(
    stand_id: int,
    payload: StandObservationCreate,
    db: Session = Depends(get_db),
) -> StandObservation:
    if db.get(Stand, stand_id) is None:
        raise HTTPException(status_code=404, detail="Stand not found")
    observation = StandObservation(
        stand_id=stand_id,
        observed_at=payload.observed_at or datetime.utcnow(),
        observer=payload.observer,
        category=payload.category,
        note=payload.note,
        properties=payload.properties,
    )
    db.add(observation)
    db.commit()
    db.refresh(observation)
    return observation


@router.patch("/{stand_id}", response_model=StandRead)
def update_stand(stand_id: int, payload: StandUpdate, db: Session = Depends(get_db)) -> Stand:
    stand = db.get(Stand, stand_id)
    if stand is None:
        raise HTTPException(status_code=404, detail="Stand not found")

    updates = payload.model_dump(exclude_unset=True)
    geometry_wkt = updates.pop("geometry_wkt", None)
    for field, value in updates.items():
        setattr(stand, field, value)
    if geometry_wkt is not None:
        stand.geometry = WKTElement(geometry_wkt, srid=4326) if geometry_wkt else None

    db.commit()
    db.refresh(stand)
    return stand


@router.delete("/{stand_id}")
def delete_stand(stand_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    stand = db.get(Stand, stand_id)
    if stand is None:
        raise HTTPException(status_code=404, detail="Stand not found")

    db.execute(text("UPDATE chat_sessions SET stand_id = NULL WHERE stand_id = :stand_id"), {"stand_id": stand_id})
    db.delete(stand)
    db.commit()
    return {"deleted": True, "id": stand_id}


@router.post("/{stand_id}/link-geometry", response_model=StandRead)
def link_stand_geometry(stand_id: int, payload: StandGeometryLink, db: Session = Depends(get_db)) -> Stand:
    stand = db.get(Stand, stand_id)
    if stand is None:
        raise HTTPException(status_code=404, detail="Stand not found")

    _validate_identifier(payload.source_schema, "source_schema")
    _validate_identifier(payload.source_table, "source_table")
    _validate_identifier(payload.source_id_column, "source_id_column")
    _validate_identifier(payload.geometry_column, "geometry_column")
    _ensure_source_geometry_exists(db, payload)

    result = db.execute(
        text(
            f"""
            UPDATE stands
            SET geometry = linked.geometry
            FROM (
                SELECT ST_GeometryN(
                    ST_CollectionExtract(
                        ST_MakeValid(ST_Force2D(ST_Transform("{payload.geometry_column}", 4326))),
                        3
                    ),
                    1
                )::geometry(POLYGON, 4326) AS geometry
                FROM "{payload.source_schema}"."{payload.source_table}"
                WHERE "{payload.source_id_column}"::text = :source_id
                  AND "{payload.geometry_column}" IS NOT NULL
                LIMIT 1
            ) AS linked
            WHERE stands.id = :stand_id
            """
        ),
        {"stand_id": stand_id, "source_id": str(payload.source_id)},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Source geometry feature not found")
    db.commit()
    db.refresh(stand)
    return stand


@router.get("/{stand_id}", response_model=StandRead)
def get_stand(stand_id: int, db: Session = Depends(get_db)) -> Stand:
    stand = db.get(Stand, stand_id)
    if stand is None:
        raise HTTPException(status_code=404, detail="Stand not found")
    return stand


def _validate_identifier(identifier: str, field_name: str) -> None:
    if not identifier.replace("_", "").isalnum() or identifier[0].isdigit():
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}")


def _ensure_source_geometry_exists(db: Session, payload: StandGeometryLink) -> None:
    column_count = db.execute(
        text(
            """
            SELECT COUNT(DISTINCT column_name)
            FROM information_schema.columns
            WHERE table_schema = :schema
              AND table_name = :table
              AND column_name IN (:id_column, :geometry_column)
            """
        ),
        {
            "schema": payload.source_schema,
            "table": payload.source_table,
            "id_column": payload.source_id_column,
            "geometry_column": payload.geometry_column,
        },
    ).scalar()
    if column_count != 2:
        raise HTTPException(status_code=404, detail="Source table or columns not found")


def _stand_geometry_summary(db: Session, stand_id: int) -> dict[str, Any] | None:
    row = db.execute(
        text(
            """
            SELECT
                ST_GeometryType(geometry) AS geometry_type,
                ST_IsValid(geometry) AS is_valid,
                ROUND((ST_Area(geometry::geography) / 10000.0)::numeric, 3) AS area_ha_geodesic,
                ROUND(ST_Perimeter(geometry::geography)::numeric, 1) AS perimeter_m,
                ROUND(ST_X(ST_Centroid(geometry))::numeric, 6) AS centroid_lon,
                ROUND(ST_Y(ST_Centroid(geometry))::numeric, 6) AS centroid_lat
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
    }
