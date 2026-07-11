from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.errors import RasterioError
from rasterio.mask import mask
from rasterio.warp import transform_geom
from sqlalchemy import text
from sqlalchemy.orm import Session

RASTER_DIR = Path("data/Raster_files")
RASTER_EXTENSIONS = {".tif", ".tiff"}


def terrain_summary_for_stand(db: Session, stand_id: int) -> dict[str, Any] | None:
    geometry = _stand_geometry_geojson(db, stand_id)
    if geometry is None:
        return None

    summaries = []
    for raster_path in sorted(_raster_files()):
        summary = _terrain_summary_for_raster(raster_path, geometry)
        if summary:
            summaries.append(summary)

    if not summaries:
        return None

    return {
        "raster_count": len(summaries),
        "rasters": summaries,
    }


def _stand_geometry_geojson(db: Session, stand_id: int) -> dict[str, Any] | None:
    row = db.execute(
        text(
            """
            SELECT ST_AsGeoJSON(geometry)::json AS geometry
            FROM stands
            WHERE id = :stand_id
              AND geometry IS NOT NULL
            """
        ),
        {"stand_id": stand_id},
    ).mappings().first()
    if row is None:
        return None
    geometry = row["geometry"]
    return json.loads(geometry) if isinstance(geometry, str) else geometry


def _raster_files() -> list[Path]:
    if not RASTER_DIR.exists():
        return []
    return [path for path in RASTER_DIR.iterdir() if path.suffix.lower() in RASTER_EXTENSIONS]


def _terrain_summary_for_raster(raster_path: Path, stand_geometry: dict[str, Any]) -> dict[str, Any] | None:
    try:
        with rasterio.open(raster_path) as src:
            if src.crs is None:
                return None
            raster_geometry = transform_geom("EPSG:4326", src.crs, stand_geometry)
            clipped, transform = mask(src, [raster_geometry], crop=True, filled=False, indexes=1)
            elevation = np.ma.masked_invalid(clipped)
            if elevation.count() == 0:
                return None

            elevation_stats = _stats(elevation)
            slope_deg, aspect_deg = _slope_and_aspect(elevation, transform)
            slope_stats = _stats(slope_deg)
            aspect_stats = _aspect_stats(aspect_deg)
            ruggedness_index = _terrain_ruggedness_index(elevation)
            ruggedness_stats = _stats(ruggedness_index)

            return {
                "raster": raster_path.name,
                "crs": str(src.crs),
                "pixel_size_m": {
                    "x": round(abs(transform.a), 3),
                    "y": round(abs(transform.e), 3),
                },
                "cell_count": int(elevation.count()),
                "altitude_m": elevation_stats,
                "slope_deg": slope_stats,
                "aspect": aspect_stats,
                "terrain_ruggedness_index_m": ruggedness_stats,
            }
    except (RasterioError, ValueError):
        return None


def _slope_and_aspect(elevation: np.ma.MaskedArray, transform) -> tuple[np.ma.MaskedArray, np.ma.MaskedArray]:
    data = elevation.astype("float64")
    filled = data.filled(np.nan)
    y_res = abs(transform.e)
    x_res = abs(transform.a)
    dz_dy, dz_dx = np.gradient(filled, y_res, x_res)

    slope = np.degrees(np.arctan(np.sqrt((dz_dx**2) + (dz_dy**2))))
    aspect = (np.degrees(np.arctan2(dz_dx, -dz_dy)) + 360) % 360

    mask_values = np.ma.getmaskarray(elevation) | ~np.isfinite(slope) | ~np.isfinite(aspect)
    return np.ma.array(slope, mask=mask_values), np.ma.array(aspect, mask=mask_values)


def _terrain_ruggedness_index(elevation: np.ma.MaskedArray) -> np.ma.MaskedArray:
    data = elevation.astype("float64").filled(np.nan)
    if data.shape[0] < 3 or data.shape[1] < 3:
        return np.ma.masked_all(data.shape, dtype="float64")

    center = data[1:-1, 1:-1]
    squared_differences = np.zeros_like(center, dtype="float64")
    valid_neighbors = np.ones_like(center, dtype=bool)

    for row_offset in (-1, 0, 1):
        for col_offset in (-1, 0, 1):
            if row_offset == 0 and col_offset == 0:
                continue
            neighbor = data[
                1 + row_offset : data.shape[0] - 1 + row_offset,
                1 + col_offset : data.shape[1] - 1 + col_offset,
            ]
            squared_differences += (neighbor - center) ** 2
            valid_neighbors &= np.isfinite(neighbor)

    tri_inner = np.sqrt(squared_differences)
    valid = np.isfinite(center) & np.isfinite(tri_inner) & valid_neighbors
    tri = np.full(data.shape, np.nan, dtype="float64")
    tri[1:-1, 1:-1] = tri_inner
    return np.ma.array(tri, mask=~np.isfinite(tri) | _edge_mask(data.shape) | _expanded_invalid_mask(elevation) | ~_inner_valid_mask(valid, data.shape))


def _edge_mask(shape: tuple[int, int]) -> np.ndarray:
    mask = np.zeros(shape, dtype=bool)
    mask[0, :] = True
    mask[-1, :] = True
    mask[:, 0] = True
    mask[:, -1] = True
    return mask


def _expanded_invalid_mask(elevation: np.ma.MaskedArray) -> np.ndarray:
    return np.ma.getmaskarray(elevation) | ~np.isfinite(elevation.filled(np.nan))


def _inner_valid_mask(inner_valid: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    valid = np.zeros(shape, dtype=bool)
    valid[1:-1, 1:-1] = inner_valid
    return valid


def _stats(values: np.ma.MaskedArray) -> dict[str, float] | None:
    clean = values.compressed()
    if clean.size == 0:
        return None
    return {
        "min": round(float(np.min(clean)), 2),
        "max": round(float(np.max(clean)), 2),
        "mean": round(float(np.mean(clean)), 2),
        "sd": round(float(np.std(clean)), 2),
    }


def _aspect_stats(aspect_deg: np.ma.MaskedArray) -> dict[str, Any] | None:
    clean = aspect_deg.compressed()
    if clean.size == 0:
        return None

    radians = np.radians(clean)
    sin_mean = float(np.mean(np.sin(radians)))
    cos_mean = float(np.mean(np.cos(radians)))
    mean_deg = (math.degrees(math.atan2(sin_mean, cos_mean)) + 360) % 360
    resultant_length = math.sqrt((sin_mean**2) + (cos_mean**2))
    circular_sd = math.degrees(math.sqrt(max(0.0, -2 * math.log(max(resultant_length, 1e-12)))))

    return {
        "mean_deg": round(mean_deg, 1),
        "sd_deg": round(circular_sd, 1),
        "dominant_direction": _aspect_direction(mean_deg),
    }


def _aspect_direction(degrees: float) -> str:
    directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    index = int(((degrees + 22.5) % 360) / 45)
    return directions[index]
