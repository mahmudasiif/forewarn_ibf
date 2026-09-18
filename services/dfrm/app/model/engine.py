"""Dynamic Flood Risk Model (DFRM) — engine.

A faithful port of the DFRM v5.2 desktop tool (``DFRM_GUI_File.py`` by
Md. Manjurul Husain Shourov) into pure, stateless functions. The GUI is gone;
the hydrology is unchanged:

* a **water level** at a river station drives everything;
* the rising/falling **limb** + water level pick a day on the design
  hydrograph, whose column name indexes the pre-computed layers;
* four graded layers (Inundation / Hazard / Risk / Vulnerability) are returned
  as GeoJSON choropleths, and a **Warning** table is joined from the warning /
  class spreadsheets.

Reference data (shapefiles + spreadsheets) lives read-only under
``DFRM_ASSETS_DIR/DFRM_Database`` and is loaded once and cached.
"""
from __future__ import annotations

import cmath
import json
import math
from functools import lru_cache
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from app.settings import settings

# --------------------------------------------------------------------------- #
# Constants — carried over verbatim from the desktop tool.
# --------------------------------------------------------------------------- #

#: River stations and their FFWC danger levels (metres).
STATIONS: dict[str, dict] = {
    "Jamuna": {"station": "Bahadurabad (Jamuna)", "danger_level": 19.05},
    "Dharla": {"station": "Kurigram (Dharla)", "danger_level": 26.5},
}
#: Unions gauged against the Dharla (Kurigram) instead of the Jamuna.
DHARLA_UNIONS = {"Un_091", "Un_094", "Un_095", "Un_110"}

LIMBS = ["Flood Increasing", "Flood Decreasing"]
MAP_LAYERS = ["Inundation", "Hazard", "Risk", "Vulnerability"]
#: Layers whose day columns are min-max normalised to 0-100 before mapping.
NORMALISED_LAYERS = {"Hazard", "Risk", "Vulnerability"}

#: Return-period GEV parameters (calibrated for Bahadurabad / Jamuna).
_RP_K, _RP_MU, _RP_SIGMA = -0.2702, 19.63, 0.5059
#: The Jamuna danger level that the desktop tool adds to a "level above
#: danger" (DL) input to recover an absolute water level.
DL_OFFSET = 19.05

# level -> (study-area id column, display-name column)
LEVEL_KEYS: dict[str, tuple[str, str]] = {
    "District": ("Dist_ID", "DISTNAME"),
    "Upazilla": ("Thana_ID", "THANAME"),
    "Union": ("Uni_ID", "UNINAME"),
    "Village": ("Vill_ID", "Village"),
}

VL_CLASSES = {0: "", 1: "Very Low", 2: "Low", 3: "Medium", 4: "High", 5: "Very High"}
DMG_CLASSES = {0: "", 1: "Very Small", 2: "Small", 3: "Medium", 4: "Big", 5: "Very Big"}


def _db_dir() -> Path:
    return Path(settings.DFRM_ASSETS_DIR) / "DFRM_Database"


# --------------------------------------------------------------------------- #
# Cached reference-data loaders.
# --------------------------------------------------------------------------- #


@lru_cache(maxsize=1)
def _study_area() -> pd.DataFrame:
    """The full village-level study-area table (names + hierarchy + river)."""
    return pd.read_excel(_db_dir() / "NRP_Study_area.xls", "Village")


@lru_cache(maxsize=None)
def _study_area_level(level: str) -> pd.DataFrame:
    """A per-level study-area sheet, indexed by its id column."""
    col_id, _ = LEVEL_KEYS[level]
    return pd.read_excel(_db_dir() / "NRP_Study_area.xls", level, index_col=col_id)


@lru_cache(maxsize=None)
def _hydrograph(river: str) -> pd.DataFrame:
    return pd.read_excel(_db_dir() / "WL_Hydrograph.xls", river)


@lru_cache(maxsize=1)
def _river_active() -> gpd.GeoDataFrame:
    return gpd.read_file(_db_dir() / "NRP_River_Active_2020.shp").to_crs(4326)


@lru_cache(maxsize=1)
def _river_corridor() -> gpd.GeoDataFrame:
    return gpd.read_file(_db_dir() / "NRP_River_Corridor_2020.shp").to_crs(4326)


@lru_cache(maxsize=None)
def _admin_outlines(layer: str) -> dict[str, gpd.GeoDataFrame]:
    """Upazila + district outlines dissolved from a layer's union geometry.

    Derived from the *same* polygons as the choropleth (per layer — the layer
    sets differ slightly, e.g. Risk has one fewer union), so the outlines trace
    the coloured units exactly with no stray edges or misaligned double lines.
    """
    base = _layer_gdf(layer)
    out: dict[str, gpd.GeoDataFrame] = {}
    for key, col in (("upazila", "Thana_ID"), ("district", "Dist_ID")):
        out[key] = base[[col, "geometry"]].dissolve(by=col).reset_index()
    return out


@lru_cache(maxsize=None)
def _layer_gdf(layer: str) -> gpd.GeoDataFrame:
    """A graded Union layer with its day columns already normalised if needed.

    Columns 0-7 are identifiers; ``day_1 .. day_365`` follow; ``geometry`` is
    last. For the graded layers the day block is min-max scaled to 0-100 across
    the *entire* layer, exactly as the desktop tool did before plotting.
    """
    gdf = gpd.read_file(_db_dir() / f"Union_{layer}.shp")
    if gdf.crs is not None:
        gdf = gdf.to_crs(4326)
    # ~19/109 polygons ship with self-intersections; buffer(0) repairs them
    # (keeps polygon type) so neighbours share clean edges and don't render gaps.
    invalid = ~gdf.geometry.is_valid
    if invalid.any():
        gdf.loc[invalid, "geometry"] = gdf.loc[invalid, "geometry"].buffer(0)
    if layer in NORMALISED_LAYERS:
        block = gdf.iloc[:, 8:-1]
        lo = block.min().min()
        hi = block.max().max()
        span = (hi - lo) or 1.0
        gdf.iloc[:, 8:-1] = (block - lo) / span * 100.0
    return gdf


@lru_cache(maxsize=None)
def _warning_sheet(name: str, level: str) -> pd.DataFrame:
    """A warning / class spreadsheet sheet, indexed by the level's id column."""
    col_id, _ = LEVEL_KEYS[level]
    return pd.read_excel(_db_dir() / f"{name}.xlsx", level, index_col=col_id, engine="openpyxl")


def warm_cache() -> None:
    """Load the light reference data once so the first request is quick."""
    _study_area()
    _river_active()
    _river_corridor()
    _admin_outlines("Inundation")


def is_ready() -> bool:
    return (_db_dir() / "NRP_Study_area.xls").exists()


# --------------------------------------------------------------------------- #
# Domain helpers.
# --------------------------------------------------------------------------- #


def river_for(level: str, area_id: str) -> str:
    """Which river gauges the given area (drives station + hydrograph)."""
    if level == "Village":
        db = _study_area()
        match = db[db.Vill_ID == area_id]
        if not match.empty and "River" in match:
            return str(match.River.iloc[0])
        return "Jamuna"
    if level == "Union":
        return "Dharla" if area_id in DHARLA_UNIONS else "Jamuna"
    return "Jamuna"


def station_info(river: str) -> dict:
    info = STATIONS.get(river, STATIONS["Jamuna"])
    return {"river": river, "station": info["station"], "danger_level": info["danger_level"]}


def resolve_water_level(value: float, kind: str) -> float:
    """A raw water level (``WL``) or a level-above-danger (``DL``) -> absolute WL.

    The desktop tool adds a fixed 19.05 m Jamuna offset for a DL input; that
    behaviour is preserved so results match the original tool.
    """
    return value + DL_OFFSET if kind == "DL" else value


def return_period(wl: float) -> float | None:
    """FFWC water level -> flood return period in years (GEV).

    Mirrors the desktop tool: for high water levels the GEV term goes negative
    and the fractional power becomes complex, so the whole expression is
    evaluated in the complex plane and the real part taken (as numpy did).
    """
    xp = 1 + (_RP_K * (wl - _RP_MU) / _RP_SIGMA)
    try:
        rp = 1 / (1 - cmath.exp(-(complex(xp) ** (-1 / _RP_K))))
    except (ValueError, ZeroDivisionError, OverflowError):
        return None
    rp = rp.real
    if not math.isfinite(rp):
        return None
    return round(rp, 2)


def hydrograph_day(river: str, wl: float, limb: str) -> str:
    """The design-hydrograph day column whose water level is closest to ``wl``."""
    hydro = _hydrograph(river)
    hydro = hydro[hydro.Limb == limb]
    idx = (hydro.WL - wl).abs().idxmin()
    return str(hydro.loc[idx].Day)


def _clean(value):
    """JSON-safe scalar: NaN/inf -> None, numpy -> python."""
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        f = float(value)
        return None if not math.isfinite(f) else f
    if isinstance(value, np.bool_):
        return bool(value)
    return value


# --------------------------------------------------------------------------- #
# Areas — the cascading picker tree.
# --------------------------------------------------------------------------- #


@lru_cache(maxsize=1)
def area_tree() -> dict:
    """The full District -> Upazilla -> Union -> Village tree for the picker."""
    db = _study_area()
    districts = []
    for dist_id, d in db.groupby("Dist_ID", sort=False):
        upazilas = []
        for thana_id, t in d.groupby("Thana_ID", sort=False):
            unions = []
            for uni_id, u in t.groupby("Uni_ID", sort=False):
                villages = [
                    {"id": str(v.Vill_ID), "name": str(v.Village), "river": str(v.River)}
                    for v in u.itertuples()
                ]
                unions.append(
                    {
                        "id": str(uni_id),
                        "name": str(u.UNINAME.iloc[0]),
                        "river": river_for("Union", str(uni_id)),
                        "villages": villages,
                    }
                )
            upazilas.append(
                {"id": str(thana_id), "name": str(t.THANAME.iloc[0]), "unions": unions}
            )
        districts.append(
            {"id": str(dist_id), "name": str(d.DISTNAME.iloc[0]), "upazilas": upazilas}
        )
    return {
        "stations": STATIONS,
        "limbs": LIMBS,
        "map_layers": MAP_LAYERS,
        "levels": list(LEVEL_KEYS.keys()),
        "districts": districts,
    }


# --------------------------------------------------------------------------- #
# Map — a graded layer as GeoJSON for the selected area.
# --------------------------------------------------------------------------- #

_ID_COLS = ["DIVNAME", "DISTNAME", "THANAME", "UNINAME", "Dist_ID", "Thana_ID", "Uni_ID"]


def _features(gdf: gpd.GeoDataFrame, value_col: str, simplify: float) -> list[dict]:
    keep = [c for c in _ID_COLS if c in gdf.columns]
    sub = gdf[[*keep, value_col, "geometry"]].copy()
    sub = sub[sub.geometry.notna() & ~sub.geometry.is_empty]
    if simplify > 0:
        sub["geometry"] = sub.geometry.simplify(simplify, preserve_topology=True)
    sub = sub.rename(columns={value_col: "value"})
    collection = json.loads(sub.to_json())
    # Scrub non-finite floats that to_json emits as bare NaN (invalid JSON).
    for feat in collection["features"]:
        feat["properties"] = {k: _clean(v) for k, v in feat["properties"].items()}
    return collection["features"]


def _river_layers(bounds, margin: float, simplify: float) -> dict:
    """River corridor + active channel clipped to the area bbox, as GeoJSON."""
    minx, miny, maxx, maxy = bounds
    out = {}
    for key, gdf in (("corridor", _river_corridor()), ("active", _river_active())):
        sub = gdf.cx[minx - margin : maxx + margin, miny - margin : maxy + margin]
        if sub.empty:
            out[key] = {"type": "FeatureCollection", "features": []}
            continue
        sub = sub.copy()
        if simplify > 0:
            sub["geometry"] = sub.geometry.simplify(simplify, preserve_topology=True)
        out[key] = json.loads(sub[["geometry"]].to_json())
    return out


_EMPTY_FC = {"type": "FeatureCollection", "features": []}


def _context_layers(bounds, layer: str, margin: float, simplify: float) -> dict:
    """Upazila + district admin outlines (from the layer's geometry) clipped to
    the area bbox, as GeoJSON. Drawn as thin context over the flood choropleth."""
    minx, miny, maxx, maxy = bounds
    outlines = _admin_outlines(layer)
    out: dict[str, dict] = {}
    for key in ("upazila", "district"):
        sub = outlines[key].cx[minx - margin : maxx + margin, miny - margin : maxy + margin]
        if sub.empty:
            out[key] = _EMPTY_FC
            continue
        sub = sub.copy()
        if simplify > 0:
            sub["geometry"] = sub.geometry.simplify(simplify, preserve_topology=True)
        out[key] = json.loads(sub[["geometry"]].to_json())
    return out


def map_layer(
    *,
    level: str,
    area_id: str,
    layer: str,
    water_level: float,
    limb: str,
    simplify: float = 0.0,
) -> dict:
    """Graded flood layer for the selected area, as a GeoJSON choropleth."""
    if layer not in MAP_LAYERS:
        raise ValueError(f"Unknown map layer '{layer}'.")
    river = river_for(level, area_id)
    day = hydrograph_day(river, water_level, limb)

    gdf = _layer_gdf(layer)
    # District/Upazilla filter by their id; Union and Village both scope to the
    # union polygon (the graded layers carry no village geometry).
    if level == "District":
        bound = gdf[gdf.Dist_ID == area_id]
    elif level == "Upazilla":
        bound = gdf[gdf.Thana_ID == area_id]
    else:  # Union or Village
        uni_id = area_id if level == "Union" else _uni_of_village(area_id)
        bound = gdf[gdf.Uni_ID == uni_id]

    if bound.empty:
        raise LookupError(f"No {layer} polygons for {level} '{area_id}'.")

    block = gdf.iloc[:, 8:-1]
    metric_min = _clean(block.min().min())
    metric_max = _clean(block.max().max())
    bounds = [float(v) for v in bound.total_bounds]
    area_name = _area_name(level, area_id)

    return {
        "level": level,
        "area_id": area_id,
        "area_name": area_name,
        "layer": layer,
        **station_info(river),
        "day": day,
        "limb": limb,
        "water_level": water_level,
        "return_period": return_period(water_level),
        "metric_min": metric_min,
        "metric_max": metric_max,
        "metric_unit": "%" if layer in NORMALISED_LAYERS else "",
        "bounds": bounds,
        "feature_count": int(len(bound)),
        "features": _features(bound, day, simplify),
        "rivers": _river_layers(bounds, margin=0.02, simplify=0.0005),
        # Outlines must use the SAME simplify as the choropleth (none) so they
        # sit exactly on the fill edge — any mismatch opens hairline slivers.
        "context": _context_layers(bounds, layer=layer, margin=0.02, simplify=simplify),
    }


def _uni_of_village(vill_id: str) -> str:
    db = _study_area()
    match = db[db.Vill_ID == vill_id]
    return str(match.Uni_ID.iloc[0]) if not match.empty else vill_id


def _area_name(level: str, area_id: str) -> str:
    _, name_col = LEVEL_KEYS[level]
    db = _study_area()
    id_col, _ = LEVEL_KEYS[level]
    match = db[db[id_col] == area_id]
    return str(match[name_col].iloc[0]) if not match.empty else area_id


# --------------------------------------------------------------------------- #
# Warning — the per-area flood warning table.
# --------------------------------------------------------------------------- #


def _wd_text(warning, wd1, wd2) -> str:
    if warning == 0 or warning is None:
        return ""
    if wd2 == 20:
        return f"above {wd1} ft"
    return f"{wd1} ft to {wd2} ft"


def _du_text(warning, du1, du2) -> str:
    if warning == 0 or warning is None:
        return ""
    try:
        return f"{int(du1)} days to {int(du2)} days"
    except (ValueError, TypeError):
        return ""


def warning(
    *,
    level: str,
    area_id: str,
    water_level: float,
    limb: str,
    date: str | None = None,
) -> dict:
    """The flood warning for the selected area + the whole-level table."""
    if level not in LEVEL_KEYS:
        raise ValueError(f"Unknown level '{level}'.")
    river = river_for(level, area_id)
    day = hydrograph_day(river, water_level, limb)

    wrn = _warning_sheet("Warning", level)
    wd1 = _warning_sheet("WD_1_cls", level)
    wd2 = _warning_sheet("WD_2_cls", level)
    du1 = _warning_sheet("Du_1_cls", level)
    du2 = _warning_sheet("Du_2_cls", level)
    vl = wrn.replace(VL_CLASSES)
    dmg = wrn.replace(DMG_CLASSES)
    std = _study_area_level(level)

    com = pd.DataFrame(
        [wrn[day], wd1[day], wd2[day], du1[day], du2[day], vl[day], dmg[day]]
    ).T
    com.columns = ["Warning", "WD1", "WD2", "Du1", "Du2", "VL", "Damage"]
    res = std.join(com)

    rows = _warning_rows(res, level)
    selected = next((r for r in rows if r.get("_id") == area_id), None)
    if selected is None:
        raise LookupError(f"No warning row for {level} '{area_id}'.")

    return {
        "level": level,
        "area_id": area_id,
        "area_name": _area_name(level, area_id),
        "day": day,
        "limb": limb,
        "date": date,
        **station_info(river),
        "water_level": water_level,
        "return_period": return_period(water_level),
        "selected": selected,
        "rows": rows,
    }


def _warning_rows(res: pd.DataFrame, level: str) -> list[dict]:
    """Every area at the level, as a display/CSV-ready warning row."""
    rows = []
    for area_id, r in res.iterrows():
        warn = r.get("Warning")
        warn = None if pd.isna(warn) else warn
        no_risk = warn == 0 or warn is None
        row = {
            "_id": str(area_id),
            "Division": _clean(r.get("DIVNAME")),
            "District": _clean(r.get("DISTNAME")),
            "Risk Level": "No Risk" if no_risk else _clean(warn),
            "Water Depth": _wd_text(warn, _clean(r.get("WD1")), _clean(r.get("WD2"))),
            "Flood Duration": _du_text(warn, r.get("Du1"), r.get("Du2")),
            "Water Speed": "" if no_risk else _clean(r.get("VL")),
            "Damage": "" if no_risk else _clean(r.get("Damage")),
        }
        if level in ("Upazilla", "Union", "Village"):
            row["Upazilla"] = _clean(r.get("THANAME"))
        if level in ("Union", "Village"):
            row["Union"] = _clean(r.get("UNINAME"))
        if level == "Village":
            row["Village"] = _clean(r.get("Village"))
        rows.append(row)
    return rows
