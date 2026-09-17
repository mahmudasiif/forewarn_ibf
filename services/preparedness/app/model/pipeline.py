import argparse
from collections import Counter
from difflib import SequenceMatcher
import json
import os
import re
import statistics
import tempfile
import threading
import warnings
import gc
import time
from pathlib import Path
from typing import NamedTuple, Sequence
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import multiprocessing

import geopandas as gpd
import shapely
import google.generativeai as genai
import numpy as np
import pandas as pd
from folium import Element
from langchain_google_genai import ChatGoogleGenerativeAI
from netCDF4 import Dataset, num2date
from PIL import Image, ImageDraw, ImageFont

import folium
import math

warnings.filterwarnings("ignore", category=FutureWarning)

CPU_CORES = max(1, multiprocessing.cpu_count() // 2)  # Use half of logical cores (physical cores)
print(f"[PARALLEL] Using {CPU_CORES} CPU cores for parallel processing", flush=True)

# Vendored from the Cyclone-AI-Guideline handover (Files/app.py). The ONLY edit
# to the vendored source is this line: the static GIS/CSV/xlsx/docx assets are
# mounted read-only into the container rather than sitting beside this module.
BASE_DATA_DIR = Path(os.getenv("PREPAREDNESS_ASSETS_DIR", "/app/assets"))

UNION_2022_SHP = Path("BD Union BBS 2022") / "BD_Union_BBS_2022.shp"
UPAZILA_2022_SHP = Path("BD Upazila BBS 2022") / "BD_Upazila_BBS_2022.shp"
DISTRICT_2022_SHP = Path("BD District BBS 2022") / "BD_District_BBS_2022.shp"
LEGACY_UNION_SHP = Path("BD_Union_BBS21.shp")

BBS2022_HOUSING_COLUMNS = {
    "Pucca": "C14HHPUCP",
    "Semi-pucca": "C14HHSPUCP",
    "Kancha": "C14HHKANP",
}

BBS2022_DEMOGRAPHIC_COLUMNS = {
    "MALE_POP": "C01MPOP",
    "FEMALE_POP": "C01FPOP",
    "AGE_0_4": "C02AG04",
    "AGE_5_19": ("C02AG59", "C02AG1014", "C02AG1519"),
    "AGE_60_PLUS": ("C02AG6064", "C02AG6569", "C02AG7074", "C02AG7579", "C02AG80PLS"),
}

DEMOGRAPHIC_AFFECTED_KEYS = (
    "male",
    "female",
    "age_0_4",
    "age_5_19",
    "age_60_plus",
)

_NETCDF_READ_LOCK = threading.Lock()


def _safe_remove(path: str, retries: int = 5, delay: float = 0.1) -> None:
    for attempt in range(retries):
        try:
            os.remove(path)
            return
        except PermissionError:
            gc.collect()
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                raise


def read_netcdf_time_metadata(nc_input: bytes | str | Path) -> dict:
    """Read CF time metadata without assuming that the coordinate is hours."""
    temp_path: str | None = None
    if isinstance(nc_input, (str, Path)):
        nc_path = str(nc_input)
    else:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".nc") as tmp:
            tmp.write(nc_input)
            nc_path = tmp.name
        temp_path = nc_path

    try:
        with _NETCDF_READ_LOCK, Dataset(nc_path, "r") as nc:
            time_var = nc.variables.get("time")
            if time_var is None or not getattr(time_var, "size", 0):
                return {"available": False}
            units = getattr(time_var, "units", "")
            calendar = getattr(time_var, "calendar", "standard")
            values = np.asarray(time_var[:], dtype=float).ravel()
            dates = num2date(
                [float(values[0]), float(values[-1])],
                units=units,
                calendar=calendar,
                only_use_cftime_datetimes=False,
                only_use_python_datetimes=False,
            )
            return {
                "available": True,
                "units": units,
                "calendar": calendar,
                "start_time_iso": dates[0].isoformat(),
                "end_time_iso": dates[-1].isoformat(),
            }
    except Exception as exc:  # noqa: BLE001 - metadata warning is non-fatal
        return {"available": False, "error": str(exc)}
    finally:
        if temp_path and os.path.exists(temp_path):
            _safe_remove(temp_path)


def get_llm(api_key: str | None = None):
    if api_key is None:
        api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        api_key = next(
            (key.strip() for key in os.getenv("GOOGLE_API_KEYS", "").split(",") if key.strip()),
            None,
        )
    if not api_key:
        raise EnvironmentError(
            "GOOGLE_API_KEYS or GOOGLE_API_KEY must be set to polish the guideline."
        )
    genai.configure(api_key=api_key)
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    # Pass the key explicitly: ChatGoogleGenerativeAI does not read the plural
    # GOOGLE_API_KEYS we configure, only GOOGLE_API_KEY/GEMINI_API_KEY or this arg.
    return ChatGoogleGenerativeAI(model=model_name, temperature=0.1, google_api_key=api_key)


def polish_guideline(guideline_template: str, polished: bool = True) -> str:
    if not polished:
        return guideline_template
    try:
        llm = get_llm()
    except Exception:  # noqa: BLE001 - any LLM setup failure must degrade, not crash the run
        warnings.warn(
            "LLM unavailable (no/invalid key or client error); returning unpolished guideline.",
            RuntimeWarning,
        )
        return guideline_template
    system_prompt = (
        "Polish the language of this impact-based cyclone preparedness guideline. "
        "DO NOT add, remove, or suggest any information, section, or advice. "
        "Do NOT give any extra comment, preface, or conclusion. "
        "JUST rewrite and improve the clarity, language, and coherence of the guideline ONLY. "
        "Output ONLY the improved text, in Markdown."
    )
    full_prompt = f"{system_prompt}\n\nGUIDELINE:\n\n{guideline_template}"
    try:
        response = llm.invoke(full_prompt)
        return response.content if hasattr(response, "content") else str(response)
    except Exception as exc:  # pragma: no cover - remote service errors
        warnings.warn(
            f"LLM polishing failed ({exc!s}); falling back to unpolished guideline.",
            RuntimeWarning,
        )
        return guideline_template


damage_table = [
    {
        "type": "Kancha",
        "thresholds": [108, 144],
        "labels": ["Roof loss/wall collapse", "Severe roof loss, likely total collapse"],
    },
    {
        "type": "Semi-pucca",
        "thresholds": [144, 180],
        "labels": ["Roof damage, wall cracks", "Severe roof & wall damage"],
    },
    {
        "type": "Pucca",
        "thresholds": [180, 216],
        "labels": ["Structural damage", "Severe structural damage (if not cyclone-resistant)"],
    },
]


def material_wind_band(ws: float) -> str:
    """Bucket used to look up MATERIAL_RULES / EVAC_RULES.

    Deliberately *not* a meteorological classification — these four bands are
    the procurement/evacuation planning tiers the material tables are keyed
    on. Wind is classified meteorologically by `get_imd_wind_category`
    (the IMD scale), which is what every label, legend and guideline uses.
    """
    if ws <= 50:
        return "30–50 (Low)"
    if ws <= 80:
        return "50–80 (Moderate)"
    if ws <= 120:
        return "80–120 (High / Cyclone)"
    return "120+ (Very High / Severe Cyclone)"


MATERIAL_RULES = {
    "30–50 (Low)": {
        "Kancha": [("GI wire", 10, "kg"), ("Wood/Bamboo", 5, "pcs"), ("Nails", 1, "kg")],
        "Semi-pucca": [("GI wire/strap", 12, "kg"), ("Wood", 4, "pcs"), ("Nails", 1, "kg")],
        "Pucca": [("Shutters (optional)", 0, "pcs")],
    },
    "50–80 (Moderate)": {
        "Kancha": [("GI wire", 15, "kg"), ("Wood", 8, "pcs"), ("Nails", 1.5, "kg")],
        "Semi-pucca": [("GI wire/strap", 18, "kg"), ("Wood", 6, "pcs"), ("Nails", 1.5, "kg")],
        "Pucca": [("Shutters", 4, "pcs"), ("Sandbags", 10, "pcs")],
    },
    "80–120 (High / Cyclone)": {
        "Kancha": [("GI wire", 20, "kg"), ("Wood", 10, "pcs"), ("Nails", 2, "kg")],
        "Semi-pucca": [("GI wire/strap", 24, "kg"), ("Wood", 8, "pcs"), ("Nails", 2, "kg")],
        "Pucca": [("Shutters", 6, "pcs"), ("Sandbags", 20, "pcs")],
    },
    "120+ (Very High / Severe Cyclone)": {
        "Kancha": [],
        "Semi-pucca": [
            ("GI wire/strap", 30, "kg"),
            ("Wood", 10, "pcs"),
            ("Nails", 2.5, "kg"),
            ("Storm bars", None, "pcs"),
            ("Ply shutters", None, "pcs"),
        ],
        "Pucca": [],
    },
}

HOUSE_TYPES_NUM = ["Kancha", "Semi-pucca", "Pucca"]

HOUSE_TYPE_NUM_COLUMNS = {
    "Kancha": "Kancha_num",
    "Semi-pucca": "Semi-pucca_num",
    "Pucca": "Pucca_num",
}

EVAC_RULES = {
    "80–120 (High / Cyclone)": {"Kancha": True},
    "120+ (Very High / Severe Cyclone)": {"Kancha": True},
}


rainfall_triggers = [
    (200, "Kancha"),
    (250, "Kancha / Semi-pucca"),
    (300, "All house types"),
]


CCM_DAMAGE_TYPES = ["Kancha", "Semi-pucca", "Pucca"]

CCM_DAMAGE_CLASS_MAP = {
    1: {"Kancha": "none", "Semi-pucca": "none", "Pucca": "none"},
    2: {"Kancha": "partial", "Semi-pucca": "none", "Pucca": "none"},
    3: {"Kancha": "full", "Semi-pucca": "none", "Pucca": "none"},
    4: {"Kancha": "full", "Semi-pucca": "partial", "Pucca": "none"},
    5: {"Kancha": "full", "Semi-pucca": "full", "Pucca": "partial"},
    6: {"Kancha": "full", "Semi-pucca": "full", "Pucca": "full"},
}


def format_ccm_damage(status: str) -> str:
    mapping = {
        "none": "No damage",
        "minor": "Minor damage",
        "partial": "Partial damage",
        "full": "Full damage",
    }
    return mapping.get((status or "").lower(), status.title() if status else "")


CCM_SURGE_UPPER_BOUNDS = [0.0, 0.1, 0.305, 0.61, 0.915, 1.22, 1.525, 1.83, 6.0]
CCM_WIND_UPPER_BOUNDS = [50, 75, 100, 125, 150, 175, 200, 225, 250]

CCM_DAMAGE_MATRIX = [
    [1, 1, 1, 2, 2, 4, 4, 4, 4],
    [1, 1, 1, 2, 2, 4, 4, 4, 4],
    [3, 3, 3, 3, 3, 4, 4, 4, 4],
    [5, 5, 5, 5, 5, 5, 5, 6, 6],
    [6, 6, 6, 6, 6, 6, 6, 6, 6],
    [6, 6, 6, 6, 6, 6, 6, 6, 6],
    [6, 6, 6, 6, 6, 6, 6, 6, 6],
    [6, 6, 6, 6, 6, 6, 6, 6, 6],
    [6, 6, 6, 6, 6, 6, 6, 6, 6],
]


def _ccm_band_index(value: float, upper_bounds: list[float]) -> int:
    """Index of the first band the value falls at or below.

    The DamageMatrix axes are upper bounds, so 105 km/h belongs to the "≤125"
    column, not the "≤100" one. Reading them as lower bounds (largest bound
    ≤ value) shifted every off-boundary reading one band down in severity and,
    for a union like Atulia at 105 km/h with no surge, reported class 1
    (no damage anywhere) where the matrix specifies class 2.

    A value above the top bound clamps to the last band — the matrix has no
    row/column beyond it, and the most severe band is the right home for it.
    """
    for index, bound in enumerate(upper_bounds):
        if value <= bound:
            return index
    return len(upper_bounds) - 1


def ccm_damage_code(wind_speed: float | None, surge_height: float | None) -> int:
    """Look up CCM damage class (1–6) from wind speed and surge height.

    Uses the 9×9 DamageMatrix from the CCM specification, with both axes read
    as upper bounds (see `_ccm_band_index`).
    """
    ws = wind_speed or 0.0
    surge = surge_height or 0.0

    s_idx = _ccm_band_index(surge, CCM_SURGE_UPPER_BOUNDS)
    w_idx = _ccm_band_index(ws, CCM_WIND_UPPER_BOUNDS)

    return CCM_DAMAGE_MATRIX[s_idx][w_idx]


def get_preparedness(typ: str) -> str:
    if typ == "Kancha":
        return (
            "- **Roof Bracing and Tying**: GI Wire/strong rope, bamboo/wood planks, nails/washers\n"
            "- **Foundation Protection**: Sandbags\n"
            "- **Wall strengthening**: Bamboo poles, ropes"
        )
    if typ == "Semi-pucca":
        return (
            "- **Roof Bracing and Tying**: GI Wire/rope, bamboo/wood\n"
            "- **Securing Doors/Windows**: Plywood, screws, bolts\n"
            "- **Foundation Protection**: Sandbags"
        )
    if typ == "Pucca":
        return "- **Securing Doors/Windows**: Plywood, screws, bolts"
    return ""


def calculate_materials_needed(household_data: pd.DataFrame, final_df: pd.DataFrame) -> pd.DataFrame:
    out_rows: list[dict] = []

    def _std_code(series: pd.Series) -> pd.Series:
        return series.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)

    household_data = household_data.copy()
    final_df = final_df.copy()
    if "GEO_CODE" in household_data.columns and "GEO_CODE" in final_df.columns:
        width = final_df["GEO_CODE"].astype(str).str.len().max()
        household_data["GEO_CODE"] = _std_code(household_data["GEO_CODE"]).str.zfill(width)
        final_df["GEO_CODE"] = _std_code(final_df["GEO_CODE"]).str.zfill(width)

    for _, row in household_data.iterrows():
        geo = row.get("GEO_CODE")
        if pd.isna(geo):
            continue

        mask = final_df["GEO_CODE"] == str(geo)
        if not mask.any():
            continue

        ws = float(final_df.loc[mask, "mean_ws_kmh"].iloc[0])
        union_name = (
            final_df.loc[mask, "UNION_NAME"].iloc[0]
            if "UNION_NAME" in final_df.columns
            else row.get("Union", "")
        )
        wcls = material_wind_band(ws)
        rules = MATERIAL_RULES.get(wcls, {})

        for htype in HOUSE_TYPES_NUM:
            houses = float(row.get(htype, 0) or 0)
            evac = EVAC_RULES.get(wcls, {}).get(htype, False)

            if not rules.get(htype) and evac:
                out_rows.append(
                    {
                        "GEO_CODE": str(geo),
                        "Union": union_name,
                        "Wind Class": wcls,
                        "Wind Speed (km/h)": ws,
                        "House Type": htype,
                        "Material": "Evacuate (no materials quantified)",
                        "Unit": "",
                        "Quantity per House": 0.0,
                        "Houses": houses,
                        "Total Quantity Needed": 0.0,
                        "Notes": "Evacuation recommended/mandatory per spec",
                    }
                )
                continue

            for mat, qty, unit in rules.get(htype, []):
                note = ""
                if qty is None:
                    note = "Not quantified in spec"
                    total = np.nan
                    qph = np.nan
                else:
                    qph = float(qty)
                    total = qph * houses

                if "optional" in mat.lower():
                    note = (note + "; " if note else "") + "Optional item"

                out_rows.append(
                    {
                        "GEO_CODE": str(geo),
                        "Union": union_name,
                        "Wind Class": wcls,
                        "Wind Speed (km/h)": ws,
                        "House Type": htype,
                        "Material": mat.replace(" (optional)", ""),
                        "Unit": unit,
                        "Quantity per House": qph,
                        "Houses": houses,
                        "Total Quantity Needed": total,
                        "Notes": note,
                    }
                )

    df_out = pd.DataFrame(out_rows)
    if not df_out.empty:
        df_out = df_out.drop_duplicates(
            subset=["GEO_CODE", "House Type", "Material", "Wind Class"],
            keep="first",
        )
    return df_out

def get_post_materials(typ: str) -> str:
    """
    Provide post‑cyclone repair and reconstruction materials for a given housing type.

    Parameters
    ----------
    typ : str
        Housing type (e.g. "Kancha", "Semi-pucca").

    Returns
    -------
    str
        Markdown formatted string describing materials needed for repair and reconstruction.
    """
    if typ == "Kancha":
        return "- CI Sheets (30-50), Bamboo/Wood (20-30 poles), Bricks (500-1000), Cement/Sand (5-10 bags), Tie-down straps/wires"
    if typ == "Semi-pucca":
        return "- Minor: CI Sheets (5-10), Bamboo/Wood (2-3 poles), Nails/Screws (1-2 kg)\n" \
               "- Moderate: CI Sheets (15-25), Bamboo/Wood (5-10), Bricks (100-200), Cement/Sand (1-2 bags)"
    if typ == "Pucca":
        return "- Reinforced concrete, steel bars, bricks, CGI sheets"
    return ""

def get_damage(wind, typ):
    for row in damage_table:
        if row["type"] == typ:
            ts = row["thresholds"]
            ls = row["labels"]
            if len(ts) == 1:
                if wind >= 0.9*ts[0]:
                    return ls[0], wind >= ts[0]*0.9
                return "Minor/No major damage", False
            if wind >= ts[1]:
                return ls[1], wind >= ts[1]*0.9
            elif wind >= ts[0]:
                return ls[0], wind >= ts[0]*0.9
            return "Minor/No major damage", False
    return "", False

def risk_color(val: str) -> str:
    """
    Map a risk category to a background colour for Excel export and map visualisation.

    Parameters
    ----------
    val : str
        The affected-population risk category (e.g. "High").

    Returns
    -------
    str
        A hex colour string. Returns an empty string if the category is unrecognised.
    """
    palette = {
        "Very High": "#d73027",
        "High": "#fc8d59",
        "Medium": "#fee08b",
        "Low": "#91cf60",
        "Very Low": "#1a9850",
    }
    return palette.get(val, "")


def affected_population_risk(percentage: object) -> str:
    """Classify risk solely from affected people as a share of population."""
    value = _safe_float(percentage)
    if value is None:
        return ""
    if value < 20.0:
        return "Very Low"
    if value < 40.0:
        return "Low"
    if value < 60.0:
        return "Medium"
    if value <= 80.0:
        return "High"
    return "Very High"

def damage_color(val: str) -> str:
    """
    Determine a cell background colour based on a textual damage description.

    Parameters
    ----------
    val : str
        Textual damage description returned by ``get_damage``.

    Returns
    -------
    str
        A hex colour code representing severity. Empty string for unknown values.
    """
    if not isinstance(val, str):
        return ''
    lower_val = val.lower()
    if "complete destruction" in lower_val or "full damage" in lower_val:
        return '#e53935'
    if "roof loss" in lower_val or "collapse" in lower_val or "severe roof" in lower_val:
        return '#ff9800'
    if "partial damage" in lower_val:
        return '#ff9800'
    if "damage" in val and "Roof" in val:
        return '#ffd54f'
    if "minor" in lower_val or "no major" in lower_val or "no damage" in lower_val:
        return '#81c784'
    return ''

def needs_white_font(bg_color: str) -> bool:
    """
    For very dark backgrounds we switch to a white font colour to retain contrast.

    Parameters
    ----------
    bg_color : str
        Hex colour code used for the background.

    Returns
    -------
    bool
        True if white font should be used, otherwise False.
    """
    return isinstance(bg_color, str) and bg_color.lower() in ['#e53935']

def row_severity(row: pd.Series) -> int:
    """
    Provide a numeric ordering for rows in the damage table based on severity.
    Lower numbers indicate more severe expected damage. This is used to sort
    the damage table consistently.

    Parameters
    ----------
    row : pandas.Series
        A row from the damage table containing damage descriptions for each
        housing type.

    Returns
    -------
    int
        A ranking from 0 (most severe) to 4 (least severe) used for sorting.
    """
    damage_cols = [col for col in row.index if col.endswith("Damage")]
    if not damage_cols:
        return 999
    score = 0
    for col in damage_cols:
        text = str(row.get(col, "")).lower()
        if "full" in text:
            score += 0
        elif "partial" in text:
            score += 1
        elif "minor" in text:
            score += 3
        elif text.strip():
            score += 2
        else:
            score += 4
    return score



def _normalize_name(name: str) -> str:
    """Normalize a name for case-insensitive, symbol-insensitive matching."""
    if not isinstance(name, str):
        return ""
    import re
    normalized = name.lower().strip()
    normalized = re.sub(r'[\-_\.\,\'\"\u200c\u200d]', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


DISTRICT_ALIASES = {
    "jessore": "jashore",
    "chittagong": "chattogram",
    "comilla": "cumilla",
    "bogra": "bogura",
    "barisal": "barishal",
    "jhalakati": "jhalokati",
    "jhalakathi": "jhalokati",
    "maulvi bazar": "moulvibazar",
    "maulvibazar": "moulvibazar",
    "netrakona": "netrokona",
    "chapai nawabganj": "chapainawabganj",
    "chapainababganj": "chapainawabganj",
}


def _normalize_district(name: str) -> str:
    """Normalize district name with alias handling for common spelling variations."""
    normalized = _normalize_name(name)
    return DISTRICT_ALIASES.get(normalized, normalized)


def _std_geo_code(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)


def _standardize_bbs2022_boundary(gdf: gpd.GeoDataFrame, level: str) -> gpd.GeoDataFrame:
    """Expose the small, stable set of BBS 2022 attributes used by the app."""
    gdf = gdf.to_crs("EPSG:4326").copy()
    gdf["GEO_CODE"] = _std_geo_code(gdf["GEO_CODE"])
    gdf["DISTRICT_NAME"] = gdf.get("DIST_N", "").fillna("").astype(str).str.strip()
    if level in {"union", "upazila"}:
        gdf["UPAZILA_NAME"] = gdf.get("UPZ_NA", "").fillna("").astype(str).str.strip()
    if level == "union":
        gdf["UNION_NAME"] = gdf.get("UNION_NAME", "").fillna("").astype(str).str.strip()

    numeric_map = {
        "TOTAL_POP": "C01TOTPOP",
        "TOTAL_HH": "C01HHTOT",
        "PUCCA_PCT": BBS2022_HOUSING_COLUMNS["Pucca"],
        "SEMI_PUCCA_PCT": BBS2022_HOUSING_COLUMNS["Semi-pucca"],
        "KANCHA_PCT": BBS2022_HOUSING_COLUMNS["Kancha"],
        "MALE_POP": BBS2022_DEMOGRAPHIC_COLUMNS["MALE_POP"],
        "FEMALE_POP": BBS2022_DEMOGRAPHIC_COLUMNS["FEMALE_POP"],
        "AGE_0_4": BBS2022_DEMOGRAPHIC_COLUMNS["AGE_0_4"],
    }
    for target, source in numeric_map.items():
        gdf[target] = pd.to_numeric(gdf.get(source), errors="coerce")
    for target in ("AGE_5_19", "AGE_60_PLUS"):
        sources = BBS2022_DEMOGRAPHIC_COLUMNS[target]
        gdf[target] = sum(
            (pd.to_numeric(gdf.get(source), errors="coerce") for source in sources),
            start=pd.Series(0.0, index=gdf.index),
        )
        gdf[target] = gdf[target].where(gdf[list(sources)].notna().any(axis=1), np.nan)
    gdf["HH_SIZE"] = np.where(
        gdf["TOTAL_HH"] > 0,
        gdf["TOTAL_POP"] / gdf["TOTAL_HH"],
        np.nan,
    )

    keep = [
        "GEO_CODE", "DISTRICT_NAME", "TOTAL_POP", "TOTAL_HH", "HH_SIZE",
        "PUCCA_PCT", "SEMI_PUCCA_PCT", "KANCHA_PCT",
        "MALE_POP", "FEMALE_POP", "AGE_0_4", "AGE_5_19", "AGE_60_PLUS",
    ]
    if level in {"union", "upazila"}:
        keep.append("UPAZILA_NAME")
    if level == "union":
        keep.append("UNION_NAME")
    keep.append("geometry")
    return gdf[[column for column in keep if column in gdf.columns]].copy()


def _read_bbs2022_boundary(shp_path: str | Path, level: str) -> gpd.GeoDataFrame:
    columns = [
        "GEO_CODE", "DIST_N", "C01TOTPOP", "C01HHTOT",
        BBS2022_DEMOGRAPHIC_COLUMNS["MALE_POP"],
        BBS2022_DEMOGRAPHIC_COLUMNS["FEMALE_POP"],
        BBS2022_DEMOGRAPHIC_COLUMNS["AGE_0_4"],
        *BBS2022_DEMOGRAPHIC_COLUMNS["AGE_5_19"],
        *BBS2022_DEMOGRAPHIC_COLUMNS["AGE_60_PLUS"],
        *BBS2022_HOUSING_COLUMNS.values(),
    ]
    if level in {"union", "upazila"}:
        columns.append("UPZ_NA")
    if level == "union":
        columns.append("UNION_NAME")
    return _standardize_bbs2022_boundary(gpd.read_file(shp_path, columns=columns), level)


def load_household_data(
    housing_excel_path: str = "union_bbs.csv",
    shp_path: str = str(UNION_2022_SHP),
    legacy_shp_path: str | Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Load 2022 union boundaries/demographics with legacy count fallbacks.

    C14 housing percentages and population come directly from the BBS 2022
    polygon. union_bbs.csv remains only for the three house-type counts. The
    old union layer is optionally read for municipality/city labels absent
    from the 2022 schema; its geometry is never used.
    """
    gdf_union_full = _read_bbs2022_boundary(shp_path, "union")

    if legacy_shp_path and Path(legacy_shp_path).exists():
        legacy = gpd.read_file(
            legacy_shp_path,
            columns=["GEO_CODE", "MUNICIPA_1", "CITY_NAME"],
            ignore_geometry=True,
        )
        legacy["GEO_CODE"] = _std_geo_code(legacy["GEO_CODE"])
        legacy = legacy.drop_duplicates("GEO_CODE")
        gdf_union_full = gdf_union_full.merge(legacy, on="GEO_CODE", how="left")
    else:
        gdf_union_full["MUNICIPA_1"] = np.nan
        gdf_union_full["CITY_NAME"] = np.nan

    fallback = pd.read_csv(housing_excel_path, dtype={"GEO_CODE": str}, encoding="utf-8-sig")
    fallback["GEO_CODE"] = _std_geo_code(fallback["GEO_CODE"])
    fallback = fallback.drop_duplicates("GEO_CODE").set_index("GEO_CODE")

    base = gdf_union_full[["GEO_CODE", "UNION_NAME", "UPAZILA_NAME"]].rename(
        columns={"UNION_NAME": "Union", "UPAZILA_NAME": "Upazila"}
    )
    df_percent = base.copy()
    percentage_sources = {
        "Pucca": ("PUCCA_PCT", "Percent_Paka_House"),
        "Semi-pucca": ("SEMI_PUCCA_PCT", "Percent_Semi-Paka_House"),
        "Kancha": ("KANCHA_PCT", "Percent_Kacha_House"),
    }
    shape_by_code = gdf_union_full.set_index("GEO_CODE")
    for target, (shape_column, fallback_column) in percentage_sources.items():
        direct = df_percent["GEO_CODE"].map(shape_by_code[shape_column])
        fallback_series = pd.to_numeric(fallback[fallback_column], errors="coerce")
        old_values = df_percent["GEO_CODE"].map(fallback_series)
        df_percent[target] = pd.to_numeric(direct, errors="coerce").fillna(old_values)

    df_number = base.copy()
    count_sources = {
        "Pucca": "Number_Paka_House",
        "Semi-pucca": "Number_Semi-Paka_House",
        "Kancha": "Number_Kacha_House",
    }
    for target, source in count_sources.items():
        df_number[target] = df_number["GEO_CODE"].map(pd.to_numeric(fallback[source], errors="coerce"))

    matched_counts = int(df_number[["Kancha", "Semi-pucca", "Pucca"]].notna().any(axis=1).sum())
    print(
        f"[load_household_data] Loaded {len(gdf_union_full)} BBS 2022 unions; "
        f"legacy house counts matched {matched_counts}",
        flush=True,
    )
    return df_percent, df_number, gdf_union_full.copy(), gdf_union_full




RAINFALL_ACCUMULATION_TARGET_HOURS = 72.0


def _rainfall_window_indices(nc, target_hours: float = RAINFALL_ACCUMULATION_TARGET_HOURS):
    """Time indices within `target_hours` of the first step, plus the span used.

    Returns (indices, hours) or (None, None) when the file has no usable time
    coordinate — callers then fall back to every step, which is what the code
    did before the window existed.
    """
    time_var = nc.variables.get("time")
    if time_var is None or not getattr(time_var, "size", 0):
        return None, None
    try:
        values = np.asarray(time_var[:], dtype=float).ravel()
        if values.size == 0:
            return None, None
        dates = num2date(
            values,
            units=getattr(time_var, "units", ""),
            calendar=getattr(time_var, "calendar", "standard"),
            only_use_cftime_datetimes=False,
            only_use_python_datetimes=False,
        )
        offsets = np.array(
            [(pd.Timestamp(str(d)) - pd.Timestamp(str(dates[0]))).total_seconds() / 3600.0 for d in dates]
        )
    except Exception:  # noqa: BLE001 - a malformed axis must not break parsing
        return None, None

    keep = np.nonzero(offsets <= target_hours + 1e-6)[0]
    if keep.size == 0:
        return None, None
    return keep, float(offsets[keep[-1]])

def parse_netcdf(nc_input: bytes | str | Path, gdf_union: gpd.GeoDataFrame) -> pd.DataFrame:
    """
    Per-union metrics keyed by GEO_CODE; keeps UNION_NAME from shapefile,
    and fills missing metrics from nearest union by centroid.
    Accepts either binary NetCDF content or a filesystem path.
    """
    temp_path: str | None = None
    if isinstance(nc_input, (str, Path)):
        nc_path = str(nc_input)
    else:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".nc") as tmp:
            tmp.write(nc_input)
            nc_path = tmp.name
        temp_path = nc_path

    try:
        with _NETCDF_READ_LOCK, Dataset(nc_path) as nc:
            lats = nc["lat"][:]
            lons = nc["lon"][:]
            u10 = nc["u10"][:]
            v10 = nc["v10"][:]
            try:
                rainnc = nc["rainnc"][:]
                rainc = nc["rainc"][:]
            except (KeyError, IndexError):
                rainnc = np.zeros_like(u10)
                rainc = np.zeros_like(u10)
            rain_idx, _rain_hours = _rainfall_window_indices(nc)
            if rain_idx is not None and rainnc.ndim >= 3 and rain_idx.size < rainnc.shape[0]:
                rainnc = rainnc[rain_idx]
                rainc = rainc[rain_idx]

        minx, miny, maxx, maxy = gdf_union.total_bounds
        pad = 0.5  # degrees padding to ensure coverage at edges
        lat_mask = (lats >= miny - pad) & (lats <= maxy + pad)
        lon_mask = (lons >= minx - pad) & (lons <= maxx + pad)

        lats = lats[lat_mask]
        lons = lons[lon_mask]

        def _slice_lat_lon(arr: np.ndarray) -> np.ndarray:
            if arr.ndim == 4:
                return arr[:, :, lat_mask, :][:, :, :, lon_mask]
            if arr.ndim == 3:
                return arr[:, lat_mask, :][:, :, lon_mask]
            if arr.ndim == 2:
                return arr[np.ix_(lat_mask, lon_mask)]
            raise ValueError(f"Unexpected array shape {arr.shape} for NetCDF variable")

        u10 = _slice_lat_lon(u10)
        v10 = _slice_lat_lon(v10)
        rainnc = _slice_lat_lon(rainnc)
        rainc = _slice_lat_lon(rainc)

        lat2d, lon2d = np.meshgrid(lats, lons, indexing="ij")

        def _collapse_max(arr: np.ndarray) -> np.ndarray:
            arr = np.asarray(arr, dtype=float)
            if arr.ndim >= 3:
                arr = np.nanmax(arr, axis=0)
            elif arr.ndim != 2:
                raise ValueError(f"Unexpected array shape {arr.shape} for NetCDF variable")

            if np.isnan(arr).all():
                return np.zeros_like(arr)

            if arr.ndim == 3:  # time collapsed but level dimension remains
                arr = arr[0]
            return arr

        ws_kmh = np.hypot(u10, v10) * 3.6
        ws_peak = _collapse_max(ws_kmh)
        total_rainfall = _collapse_max(rainnc + rainc)

        full_grid = pd.DataFrame({
            "lat": lat2d.ravel(),
            "lon": lon2d.ravel(),
            "ws_kmh": ws_peak.ravel(),
            "total_rainfall": total_rainfall.ravel(),
        })

        gdf_pts = gpd.GeoDataFrame(
            full_grid,
            geometry=gpd.points_from_xy(full_grid.lon, full_grid.lat),
            crs="EPSG:4326",
        )

        joined = gpd.sjoin(
            gdf_pts,
            gdf_union[["GEO_CODE", "UNION_NAME", "geometry"]],
            how="inner",
            predicate="within",
        ).dropna(subset=["GEO_CODE"])

        aggregated = joined.groupby("GEO_CODE").agg(
            mean_ws_kmh=("ws_kmh", "mean"),
            peak_ws_kmh=("ws_kmh", "max"),
            max_total_rainfall=("total_rainfall", "max"),
        ).reset_index()

        admin_columns = [
            column
            for column in (
                "GEO_CODE", "UNION_NAME", "UPAZILA_NAME", "DISTRICT_NAME",
                "MUNICIPA_1", "CITY_NAME", "TOTAL_POP", "TOTAL_HH", "HH_SIZE",
                "MALE_POP", "FEMALE_POP", "AGE_0_4", "AGE_5_19", "AGE_60_PLUS", "geometry",
            )
            if column in gdf_union.columns
        ]
        gdf_all = gdf_union[admin_columns].merge(
            aggregated, on="GEO_CODE", how="left"
        )

        gdf_all = fill_missing_with_nearest_union(gdf_all, "mean_ws_kmh")
        gdf_all = fill_missing_with_nearest_union(gdf_all, "peak_ws_kmh")
        gdf_all = fill_missing_with_nearest_union(gdf_all, "max_total_rainfall")

        return gdf_all.drop(columns="geometry")
    finally:
        if temp_path and os.path.exists(temp_path):
            _safe_remove(temp_path)


def parse_rainfall_netcdf(nc_input: bytes | str | Path, gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """Aggregate a standalone rainfall NetCDF to an administrative boundary.

    This is intentionally separate from ``parse_netcdf``: the wind upload no
    longer has to contain ``rainnc``/``rainc`` when rainfall is provided in its
    own NetCDF file.
    """
    temp_path: str | None = None
    if isinstance(nc_input, (str, Path)):
        nc_path = str(nc_input)
    else:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".nc") as tmp:
            tmp.write(nc_input)
            nc_path = tmp.name
        temp_path = nc_path
    try:
        with _NETCDF_READ_LOCK, Dataset(nc_path) as nc:
            lats = np.asarray(nc["lat"][:])
            lons = np.asarray(nc["lon"][:])
            if "rainnc" not in nc.variables or "rainc" not in nc.variables:
                raise ValueError("Rainfall NetCDF must contain rainnc and rainc variables.")
            rainnc = np.asarray(nc["rainnc"][:], dtype=float)
            rainc = np.asarray(nc["rainc"][:], dtype=float)
            rain_idx, _ = _rainfall_window_indices(nc)
            if rain_idx is not None and rainnc.ndim >= 3 and rain_idx.size < rainnc.shape[0]:
                rainnc, rainc = rainnc[rain_idx], rainc[rain_idx]
        rainfall = np.asarray(rainnc + rainc, dtype=float)
        if rainfall.ndim >= 3:
            rainfall = np.nanmax(rainfall, axis=0)
        if rainfall.ndim == 3:
            rainfall = rainfall[0]
        if rainfall.ndim != 2:
            raise ValueError(f"Unexpected rainfall array shape {rainfall.shape}")
        lat2d, lon2d = np.meshgrid(lats, lons, indexing="ij")
        points = gpd.GeoDataFrame(
            {"max_total_rainfall": rainfall.ravel()},
            geometry=gpd.points_from_xy(lon2d.ravel(), lat2d.ravel()),
            crs="EPSG:4326",
        )
        joined = gpd.sjoin(
            points, gdf[["GEO_CODE", "geometry"]], how="inner", predicate="within"
        ).dropna(subset=["GEO_CODE"])
        aggregated = joined.groupby("GEO_CODE", as_index=False)["max_total_rainfall"].max()
        admin_columns = [column for column in gdf.columns if column != "geometry"]
        merged = gdf[admin_columns + ["geometry"]].merge(aggregated, on="GEO_CODE", how="left")
        merged = fill_missing_with_nearest_union(merged, "max_total_rainfall")
        return merged.drop(columns="geometry")
    finally:
        if temp_path and os.path.exists(temp_path):
            _safe_remove(temp_path)


def parse_storm_surge(nc_input: bytes | str | Path, gdf_union: gpd.GeoDataFrame) -> pd.DataFrame:
    """Aggregate the maximum storm surge height (variable ``z``) per union.

    Handles fill/missing values (e.g. 1e20, -999) by converting them to NaN
    and returning 0 for unions with no valid surge data.
    
    OPTIMIZED: Uses vectorized spatial join instead of per-polygon loops.
    """
    temp_path: str | None = None
    if isinstance(nc_input, (str, Path)):
        nc_path = str(nc_input)
    else:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".nc") as tmp:
            tmp.write(nc_input)
            nc_path = tmp.name
        temp_path = nc_path

    try:
        with _NETCDF_READ_LOCK, Dataset(nc_path, "r") as nc:
            if "z" not in nc.variables:
                raise KeyError("Storm surge file must contain 'z' variable")

            lats = nc["lat"][:]
            lons = nc["lon"][:]
            z_var = nc["z"]
            z = z_var[:].astype(float)

            fill_values: list[float] = []
            for attr in ("_FillValue", "missing_value"):
                if hasattr(z_var, attr):
                    fill_values.append(float(getattr(z_var, attr)))
            for fv in fill_values:
                z[z == fv] = np.nan
            z[z > 1e10] = np.nan
            z[z < -100] = np.nan

        minx, miny, maxx, maxy = gdf_union.total_bounds
        pad = 0.5
        lat_mask = (lats >= miny - pad) & (lats <= maxy + pad)
        lon_mask = (lons >= minx - pad) & (lons <= maxx + pad)

        lats = lats[lat_mask]
        lons = lons[lon_mask]
        if z.ndim == 3:
            z = z[:, lat_mask, :][:, :, lon_mask]
            z_max = np.nanmax(z, axis=0)
        elif z.ndim == 2:
            z = z[np.ix_(lat_mask, lon_mask)]
            z_max = z
        else:
            raise ValueError(f"Unexpected surge array shape {z.shape}")

        lat2d, lon2d = np.meshgrid(lats, lons, indexing="ij")

        df = pd.DataFrame({
            "lat": lat2d.ravel(),
            "lon": lon2d.ravel(),
            "storm_surge_m": z_max.ravel(),
        })
        gdf_pts = gpd.GeoDataFrame(
            df,
            geometry=gpd.points_from_xy(df.lon, df.lat),
            crs="EPSG:4326",
        )

        joined = gpd.sjoin(
            gdf_pts,
            gdf_union[["GEO_CODE", "UNION_NAME", "geometry"]],
            how="inner",
            predicate="within",
        )

        aggregated = joined.groupby("GEO_CODE").agg(
            max_storm_surge_m=("storm_surge_m", "max"),
        ).reset_index()

        gdf_all = gdf_union[
            ["GEO_CODE", "UNION_NAME", "UPAZILA_NAME", "DISTRICT_NAME", "geometry"]
        ].merge(
            aggregated, on="GEO_CODE", how="left"
        )
        gdf_all["max_storm_surge_m"] = gdf_all["max_storm_surge_m"].fillna(0.0)

        return gdf_all.drop(columns="geometry")
    finally:
        if temp_path and os.path.exists(temp_path):
            _safe_remove(temp_path)



def load_district_shapefile(shp_path: str = str(DISTRICT_2022_SHP)) -> gpd.GeoDataFrame:
    """Load the district shapefile — the single source of district boundaries.

    District extents were previously only implied by grouping upazilas on the
    DISTRICT_N attribute, which gives correct statistics but no geometry. This
    layer supplies the real outline used for district-focused maps.
    """
    return _read_bbs2022_boundary(shp_path, "district")


def load_upazila_shapefile(shp_path: str = str(UPAZILA_2022_SHP)) -> gpd.GeoDataFrame:
    """Load the Upazila shapefile for use in full-coverage maps."""
    return _read_bbs2022_boundary(shp_path, "upazila")



TABULAR_FORECAST_EXTENSIONS = {".csv", ".xlsx", ".xls"}
TABULAR_FORECAST_COLUMNS = {
    "surgeheightm": "Surge Height (m)",
    "windspeedkmhr": "Wind Speed (km/hr)",
    "uniongeo": "Union_Geo",
    "union": "Union",
    "upazila": "Upazila",
    "district": "District",
}

TABULAR_FORECAST_OPTIONAL_COLUMNS = {
    "72hrcumulativerainfallmm": "72hr Cumulative Rainfall (mm)",
}
TABULAR_RAINFALL_COLUMN = "72hr Cumulative Rainfall (mm)"

TABULAR_ADMIN_COLUMNS = ("Union_Geo", "Union", "Upazila", "District")
TABULAR_HAZARD_COLUMNS = {
    "wind": "Wind Speed (km/hr)",
    "rainfall": TABULAR_RAINFALL_COLUMN,
    "surge": "Surge Height (m)",
}


def _normalise_tabular_header(value: object) -> str:
    """Make spreadsheet headers insensitive to spacing and punctuation."""
    return re.sub(r"[^a-z0-9]", "", str(value or "").strip().lower())


def read_tabular_hazard(path: str | Path, hazard: str) -> pd.DataFrame:
    """Read one independently-uploaded tabular hazard file.

    Each file carries its own hazard column plus the administrative columns
    needed to attach it to the BBS boundary.  Keeping this normalisation here
    lets wind, rainfall and surge be uploaded as CSV/XLS/XLSX independently.
    """
    if hazard not in TABULAR_HAZARD_COLUMNS:
        raise ValueError(f"Unsupported tabular hazard: {hazard}")
    input_path = Path(path).expanduser().resolve()
    suffix = input_path.suffix.lower()
    if suffix not in TABULAR_FORECAST_EXTENSIONS:
        raise ValueError("Hazard table must be a .csv, .xlsx, or .xls file.")
    if suffix == ".csv":
        try:
            raw = pd.read_csv(input_path, dtype={"Union_Geo": str}, encoding="utf-8-sig")
        except UnicodeDecodeError:
            raw = pd.read_csv(input_path, dtype={"Union_Geo": str}, encoding="latin-1")
    else:
        raw = pd.read_excel(input_path, sheet_name=0, dtype={"Union_Geo": str})
    raw = raw.dropna(how="all").copy()
    headers = {_normalise_tabular_header(column): column for column in raw.columns}
    required = [*TABULAR_ADMIN_COLUMNS, TABULAR_HAZARD_COLUMNS[hazard]]
    missing = [column for column in required if _normalise_tabular_header(column) not in headers]
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(missing))
    rename = {headers[_normalise_tabular_header(column)]: column for column in required}
    table = raw.rename(columns=rename)[required].copy()
    if table.empty:
        raise ValueError("The uploaded hazard table contains no data rows.")
    for column in TABULAR_ADMIN_COLUMNS:
        table[column] = table[column].fillna("").astype(str).str.strip()
    table["Union_Geo"] = table["Union_Geo"].str.replace(r"\.0$", "", regex=True)
    value_column = TABULAR_HAZARD_COLUMNS[hazard]
    values = pd.to_numeric(table[value_column], errors="coerce")
    invalid = values.isna() | (values < 0)
    if invalid.any():
        rows = ", ".join(str(int(index) + 2) for index in table.index[invalid][:10])
        raise ValueError(f"{value_column} must contain non-negative numbers. Invalid row(s): {rows}")
    table[value_column] = values.astype(float)
    return table


def parse_tabular_hazard(
    path: str | Path,
    hazard: str,
    gdf_union_full: gpd.GeoDataFrame,
    gdf_upazila: gpd.GeoDataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Adapt a single-hazard table to the established tabular parser.

    The existing matcher already has careful BBS/legacy-code reconciliation.
    Supply harmless zeroes for the two absent hazards, then retain only the
    requested result column after that matcher has resolved the boundaries.
    """
    table = read_tabular_hazard(path, hazard)
    for metric, column in TABULAR_HAZARD_COLUMNS.items():
        if metric not in {hazard}:
            table[column] = 0.0
    ordered = [*TABULAR_FORECAST_COLUMNS.values(), TABULAR_RAINFALL_COLUMN]
    table = table[ordered]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
        table.to_csv(tmp, index=False)
        temp_path = tmp.name
    try:
        union, upazila, metadata = parse_tabular_forecast(temp_path, gdf_union_full, gdf_upazila)
        if "BOUNDARY_GEO_CODE" in union.columns:
            boundary = union["BOUNDARY_GEO_CODE"].fillna("").astype(str).str.strip()
            union = union.copy()
            union.loc[boundary != "", "GEO_CODE"] = boundary[boundary != ""]
        return union, upazila, metadata
    finally:
        _safe_remove(temp_path)


def read_tabular_forecast(path: str | Path) -> pd.DataFrame:
    """Read and validate the user-facing CSV/XLSX forecast schema."""
    input_path = Path(path).expanduser().resolve()
    suffix = input_path.suffix.lower()
    if suffix not in TABULAR_FORECAST_EXTENSIONS:
        raise ValueError("Tabular forecast must be a .csv or .xlsx file.")

    if suffix == ".csv":
        try:
            raw = pd.read_csv(input_path, dtype={"Union_Geo": str}, encoding="utf-8-sig")
        except UnicodeDecodeError:
            raw = pd.read_csv(input_path, dtype={"Union_Geo": str}, encoding="latin-1")
    else:
        raw = pd.read_excel(input_path, sheet_name=0, dtype={"Union_Geo": str})

    raw = raw.dropna(how="all").copy()
    header_lookup = {_normalise_tabular_header(column): column for column in raw.columns}
    missing = [
        display
        for key, display in TABULAR_FORECAST_COLUMNS.items()
        if key not in header_lookup
    ]
    if missing:
        raise ValueError(
            "Missing required forecast columns: " + ", ".join(missing)
        )

    present_optional = {
        key: display
        for key, display in TABULAR_FORECAST_OPTIONAL_COLUMNS.items()
        if key in header_lookup
    }
    rename_map = {header_lookup[key]: display for key, display in TABULAR_FORECAST_COLUMNS.items()}
    rename_map.update({header_lookup[key]: display for key, display in present_optional.items()})
    table = raw.rename(columns=rename_map)[
        [*TABULAR_FORECAST_COLUMNS.values(), *present_optional.values()]
    ].copy()
    if table.empty:
        raise ValueError("The uploaded forecast table contains no data rows.")

    for column in ("Union_Geo", "Union", "Upazila", "District"):
        table[column] = table[column].fillna("").astype(str).str.strip()
    table["Union_Geo"] = table["Union_Geo"].str.replace(r"\.0$", "", regex=True)

    for column in ("Surge Height (m)", "Wind Speed (km/hr)"):
        numeric = pd.to_numeric(table[column], errors="coerce")
        invalid = numeric.isna() | (numeric < 0)
        if invalid.any():
            rows = ", ".join(str(int(index) + 2) for index in table.index[invalid][:10])
            suffix_text = "…" if int(invalid.sum()) > 10 else ""
            raise ValueError(
                f"{column} must contain non-negative numbers. Invalid spreadsheet row(s): {rows}{suffix_text}"
            )
        table[column] = numeric.astype(float)

    for column in present_optional.values():
        table[column] = pd.to_numeric(table[column], errors="coerce").clip(lower=0).fillna(0.0)

    blank_admin = (
        table[["Union_Geo", "Union", "Upazila", "District"]]
        .replace("", np.nan)
        .isna()
        .any(axis=1)
    )
    if blank_admin.any():
        rows = ", ".join(str(int(index) + 2) for index in table.index[blank_admin][:10])
        raise ValueError(
            "Union_Geo, Union, Upazila, and District are required on every data row. "
            f"Blank value row(s): {rows}"
        )
    return table.reset_index(drop=True)


def _best_unique_name_match(value: str, candidates: list[str], threshold: float) -> str | None:
    """Return a conservative fuzzy match, rejecting ambiguous candidates."""
    unique = sorted({candidate for candidate in candidates if candidate})
    scored = sorted(
        ((SequenceMatcher(None, value, candidate).ratio(), candidate) for candidate in unique),
        reverse=True,
    )
    if not scored or scored[0][0] < threshold:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.05:
        return None
    return scored[0][1]


def parse_tabular_forecast(
    path: str | Path,
    gdf_union_full: gpd.GeoDataFrame,
    gdf_upazila: gpd.GeoDataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Match direct forecast rows to BBS 2022 areas and build pipeline weather tables.

    Modern 13-digit ``Union_Geo`` values are matched exactly. Older files (such
    as the supplied Remal CSV) use legacy 8-digit codes, so those rows are
    matched conservatively by district, upazila, and union name instead.
    Every uploaded row remains available. A conservative district-wide name
    fallback handles unions that moved to a different upazila between older
    files and BBS 2022; rows without a unique match simply lack map and current
    demographic enrichment rather than being dropped or invented.
    """
    table = read_tabular_forecast(path)
    gis = gdf_union_full.copy()
    required_gis = {"GEO_CODE", "UNION_NAME", "UPAZILA_NAME", "DISTRICT_NAME"}
    missing_gis = required_gis - set(gis.columns)
    if missing_gis:
        raise ValueError("BBS 2022 union boundaries are missing: " + ", ".join(sorted(missing_gis)))

    gis["GEO_CODE"] = gis["GEO_CODE"].fillna("").astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    gis["_district"] = gis["DISTRICT_NAME"].map(_norm_district_key)
    gis["_upazila"] = gis["UPAZILA_NAME"].map(_norm_place_key)
    gis["_union"] = gis["UNION_NAME"].map(_norm_place_key)
    exact_codes = {
        _safe_str(row["GEO_CODE"]): index
        for index, row in gis.iterrows()
        if _safe_str(row.get("GEO_CODE"))
    }

    matches: list[dict] = []
    unmatched: list[dict] = []
    for input_index, input_row in table.iterrows():
        supplied_code = _safe_str(input_row.get("Union_Geo"))
        gis_index = exact_codes.get(supplied_code)
        match_method = "exact_union_geo"

        if gis_index is None:
            district_key = _norm_district_key(input_row.get("District"))
            upazila_key = _norm_place_key(input_row.get("Upazila"))
            union_key = _norm_place_key(input_row.get("Union"))
            candidates = gis[gis["_district"] == district_key]
            upazila_keys = candidates["_upazila"].dropna().astype(str).tolist()
            resolved_upazila = (
                upazila_key
                if upazila_key in set(upazila_keys)
                else _best_unique_name_match(upazila_key, upazila_keys, 0.76)
            )
            if resolved_upazila:
                candidates = candidates[candidates["_upazila"] == resolved_upazila]
            else:
                candidates = candidates.iloc[0:0]

            exact_union = candidates[candidates["_union"] == union_key]
            if len(exact_union) == 1:
                gis_index = exact_union.index[0]
                match_method = "administrative_names"
            elif not candidates.empty:
                resolved_union = _best_unique_name_match(
                    union_key,
                    candidates["_union"].dropna().astype(str).tolist(),
                    0.80,
                )
                fuzzy_union = candidates[candidates["_union"] == resolved_union] if resolved_union else candidates.iloc[0:0]
                if len(fuzzy_union) == 1:
                    gis_index = fuzzy_union.index[0]
                    match_method = "fuzzy_administrative_names"

            if gis_index is None:
                district_candidates = gis[gis["_district"] == district_key]
                exact_district_union = district_candidates[
                    district_candidates["_union"] == union_key
                ]
                if len(exact_district_union) == 1:
                    gis_index = exact_district_union.index[0]
                    match_method = "district_union_name_after_admin_change"
                elif not district_candidates.empty:
                    resolved_district_union = _best_unique_name_match(
                        union_key,
                        district_candidates["_union"].dropna().astype(str).tolist(),
                        0.84,
                    )
                    fuzzy_district_union = (
                        district_candidates[
                            district_candidates["_union"] == resolved_district_union
                        ]
                        if resolved_district_union
                        else district_candidates.iloc[0:0]
                    )
                    if len(fuzzy_district_union) == 1:
                        gis_index = fuzzy_district_union.index[0]
                        match_method = "fuzzy_district_union_after_admin_change"

        if gis_index is None:
            unmatched_item = {
                "spreadsheet_row": int(input_index) + 2,
                "union_geo": supplied_code,
                "union": _safe_str(input_row.get("Union")),
                "upazila": _safe_str(input_row.get("Upazila")),
                "district": _safe_str(input_row.get("District")),
            }
            unmatched.append(unmatched_item)
            gis_row = None
            match_method = "no_bbs2022_boundary_match"
        else:
            gis_row = gis.loc[gis_index]

        analysis_geo = (
            supplied_code
            if match_method == "exact_union_geo"
            else f"tabular:{supplied_code or int(input_index) + 2}"
        )
        output = {
            "GEO_CODE": analysis_geo,
            "BOUNDARY_GEO_CODE": _safe_str(gis_row.get("GEO_CODE")) if gis_row is not None else "",
            "UNION_NAME": _safe_str(input_row.get("Union")),
            "UPAZILA_NAME": _safe_str(input_row.get("Upazila")),
            "DISTRICT_NAME": _safe_str(input_row.get("District")),
            "MUNICIPA_1": gis_row.get("MUNICIPA_1") if gis_row is not None and "MUNICIPA_1" in gis.columns else None,
            "CITY_NAME": gis_row.get("CITY_NAME") if gis_row is not None and "CITY_NAME" in gis.columns else None,
            "TOTAL_POP": gis_row.get("TOTAL_POP") if gis_row is not None and "TOTAL_POP" in gis.columns else None,
            "HH_SIZE": gis_row.get("HH_SIZE") if gis_row is not None and "HH_SIZE" in gis.columns else None,
            "TOTAL_HH": gis_row.get("TOTAL_HH") if gis_row is not None and "TOTAL_HH" in gis.columns else None,
        }
        for column in ("MALE_POP", "FEMALE_POP", "AGE_0_4", "AGE_5_19", "AGE_60_PLUS"):
            output[column] = (
                gis_row.get(column)
                if gis_row is not None and column in gis.columns
                else None
            )
        wind = float(input_row["Wind Speed (km/hr)"])
        output.update({
            "mean_ws_kmh": wind,
            "peak_ws_kmh": wind,
            "max_total_rainfall": float(input_row.get(TABULAR_RAINFALL_COLUMN, 0.0) or 0.0),
            "max_storm_surge_m": float(input_row["Surge Height (m)"]),
            "_match_method": match_method,
            "_spreadsheet_row": int(input_index) + 2,
        })
        matches.append(output)

    matched = pd.DataFrame(matches)
    rainfall_supplied = TABULAR_RAINFALL_COLUMN in table.columns
    duplicate_count = int(matched.duplicated(subset=["GEO_CODE"]).sum())
    if duplicate_count:
        admin_columns = [
            column for column in (
                "BOUNDARY_GEO_CODE", "UNION_NAME", "UPAZILA_NAME", "DISTRICT_NAME", "MUNICIPA_1",
                "CITY_NAME", "TOTAL_POP", "TOTAL_HH", "HH_SIZE", "_match_method", "_spreadsheet_row",
                "MALE_POP", "FEMALE_POP", "AGE_0_4", "AGE_5_19", "AGE_60_PLUS",
            ) if column in matched.columns
        ]
        aggregation = {column: "first" for column in admin_columns}
        aggregation.update({
            "mean_ws_kmh": "max",
            "peak_ws_kmh": "max",
            "max_total_rainfall": "max",
            "max_storm_surge_m": "max",
        })
        matched = matched.groupby("GEO_CODE", as_index=False).agg(aggregation)
    matched = matched.drop_duplicates(subset=["GEO_CODE"]).reset_index(drop=True)

    upazila_weather = matched.groupby(
        ["DISTRICT_NAME", "UPAZILA_NAME"], as_index=False, dropna=False
    ).agg(
        mean_ws_kmh=("mean_ws_kmh", "mean"),
        peak_ws_kmh=("peak_ws_kmh", "max"),
        max_total_rainfall=("max_total_rainfall", "max"),
        max_storm_surge_m=("max_storm_surge_m", "max"),
    )
    upazila_codes: dict[tuple[str, str], str] = {}
    upazila_gis = gdf_upazila.copy()
    if {"GEO_CODE", "UPAZILA_NAME", "DISTRICT_NAME"}.issubset(upazila_gis.columns):
        for _, row in upazila_gis.iterrows():
            key = (
                _norm_district_key(row.get("DISTRICT_NAME")),
                _norm_place_key(row.get("UPAZILA_NAME")),
            )
            upazila_codes.setdefault(key, _safe_str(row.get("GEO_CODE")))
    upazila_weather["GEO_CODE"] = upazila_weather.apply(
        lambda row: upazila_codes.get(
            (_norm_district_key(row["DISTRICT_NAME"]), _norm_place_key(row["UPAZILA_NAME"])),
            f"upazila:{row['DISTRICT_NAME']}|{row['UPAZILA_NAME']}",
        ),
        axis=1,
    )
    direct_columns = [
        column for column in (
            "GEO_CODE", "TOTAL_POP", "TOTAL_HH", "HH_SIZE",
            "PUCCA_PCT", "SEMI_PUCCA_PCT", "KANCHA_PCT",
            "MALE_POP", "FEMALE_POP", "AGE_0_4", "AGE_5_19", "AGE_60_PLUS",
        ) if column in upazila_gis.columns
    ]
    if len(direct_columns) > 1:
        upazila_weather = upazila_weather.merge(
            upazila_gis[direct_columns].drop_duplicates("GEO_CODE"),
            on="GEO_CODE",
            how="left",
        )

    metadata = {
        "input_type": "tabular",
        "input_rows": int(len(table)),
        "available_area_rows": int(len(matched)),
        "boundary_matched_rows": int(len(table) - len(unmatched)),
        "unmatched_rows": int(len(unmatched)),
        "duplicate_area_rows": duplicate_count,
        "unmatched_examples": unmatched[:10],
        "rainfall_supplied": rainfall_supplied,
    }
    if rainfall_supplied:
        metadata["rainfall_accumulation_hours"] = RAINFALL_ACCUMULATION_TARGET_HOURS
        metadata["rainfall_target_hours"] = RAINFALL_ACCUMULATION_TARGET_HOURS
    return matched, upazila_weather, metadata


MAP_SIMPLIFY_TOLERANCE = 0.0008


def _polygonal_or_none(geom):
    """Repair a geometry and keep it polygonal, or return None if impossible."""
    if geom is None or geom.is_empty:
        return None
    if geom.is_valid:
        return geom
    repaired = shapely.make_valid(geom)
    if repaired is None or repaired.is_empty:
        return None
    if repaired.geom_type in ("Polygon", "MultiPolygon"):
        return repaired
    parts = [p for p in getattr(repaired, "geoms", []) if p.geom_type in ("Polygon", "MultiPolygon")]
    if not parts:
        return None
    return parts[0] if len(parts) == 1 else shapely.union_all(parts)


def _simplify_for_maps(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Return a copy of ``gdf`` with simplified geometry, for Folium rendering only.

    Uses **coverage** simplification, not per-polygon simplification. Shapely's
    ordinary ``simplify(preserve_topology=True)`` guarantees each polygon stays
    individually valid but knows nothing about its neighbours, so two unions
    sharing a border each keep a different subset of the vertices along that
    shared edge. The edges no longer coincide and the map shows white slivers
    where they pull apart and darker seams where they overlap — measured on the
    coastal districts, per-polygon simplification introduced 3.5e-3 deg² of
    overlap and 3.7e-3 deg² of gaps against a source coverage that had ~1e-10
    of each, and left geometry so broken that GEOS refused to union it.

    ``coverage_simplify`` simplifies the shared edges once and gives the result
    to both neighbours, so boundaries stay perfectly coincident (measured
    overlap/gaps stay at the source's ~1e-9 noise floor).
    """
    simplified = gdf.copy()
    geometries = simplified.geometry.values

    try:
        result = shapely.coverage_simplify(
            geometries, tolerance=MAP_SIMPLIFY_TOLERANCE, simplify_boundary=True
        )
    except Exception as exc:  # noqa: BLE001 - never lose the maps over this
        print(f"[gis] coverage simplification failed ({exc}); using full-precision geometry", flush=True)
        return simplified

    repaired = [
        cleaned if (cleaned := _polygonal_or_none(candidate)) is not None else original
        for candidate, original in zip(result, geometries)
    ]
    simplified["geometry"] = gpd.GeoSeries(repaired, index=simplified.index, crs=gdf.crs)
    return simplified


def load_all_gis_data(data_dir: str | Path | None = None) -> dict:
    """Load and preprocess every static GIS/housing asset exactly once.

    Bundles ``load_household_data()`` + ``load_upazila_shapefile()`` and adds
    lighter-weight simplified-geometry copies used only for Folium map
    rendering (smaller HTML, faster draw). This is the expensive, disk-bound
    step (reading + reprojecting ~80MB of shapefiles); callers that serve
    many requests (see ``service.py``) should call this once and reuse the
    result via the ``preloaded`` argument of ``process_cyclone`` instead of
    letting every request pay this cost again.
    """
    data_path = _resolve_data_dir(data_dir)

    df_percent, df_number, gdf_union, gdf_union_full = load_household_data(
        housing_excel_path=str(data_path / "union_bbs.csv"),
        shp_path=str(data_path / UNION_2022_SHP),
        legacy_shp_path=str(data_path / LEGACY_UNION_SHP),
    )
    gdf_upazila = load_upazila_shapefile(str(data_path / UPAZILA_2022_SHP))

    gdf_union_map = _simplify_for_maps(gdf_union)
    gdf_upazila_map = _simplify_for_maps(gdf_upazila)

    gdf_district = load_district_shapefile(str(data_path / DISTRICT_2022_SHP))

    return {
        "data_path": data_path,
        "df_percent": df_percent,
        "df_number": df_number,
        "gdf_union": gdf_union,
        "gdf_union_full": gdf_union_full,
        "gdf_upazila": gdf_upazila,
        "gdf_district": gdf_district,
        "gdf_union_map": gdf_union_map,
        "gdf_upazila_map": gdf_upazila_map,
    }


def copy_gis_bundle(bundle: dict) -> dict:
    """Shallow-copy every DataFrame/GeoDataFrame in a ``load_all_gis_data()``
    bundle. Use this when handing a long-lived cached bundle to a single
    request so downstream code is free to mutate its copies without
    corrupting the shared cache used by later requests."""
    return {
        key: (value.copy() if hasattr(value, "copy") else value)
        for key, value in bundle.items()
    }


def parse_netcdf_upazila(nc_input: bytes | str | Path, gdf_upazila: gpd.GeoDataFrame) -> pd.DataFrame:
    """
    Parse NetCDF at Upazila level for faster full-coverage maps.
    Returns per-upazila metrics keyed by GEO_CODE.
    """
    temp_path: str | None = None
    if isinstance(nc_input, (str, Path)):
        nc_path = str(nc_input)
    else:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".nc") as tmp:
            tmp.write(nc_input)
            nc_path = tmp.name
        temp_path = nc_path

    try:
        with _NETCDF_READ_LOCK, Dataset(nc_path) as nc:
            lats = nc["lat"][:]
            lons = nc["lon"][:]
            u10 = nc["u10"][:]
            v10 = nc["v10"][:]
            try:
                rainnc = nc["rainnc"][:]
                rainc = nc["rainc"][:]
            except (KeyError, IndexError):
                rainnc = np.zeros_like(u10)
                rainc = np.zeros_like(u10)
            rain_idx, _rain_hours = _rainfall_window_indices(nc)
            if rain_idx is not None and rainnc.ndim >= 3 and rain_idx.size < rainnc.shape[0]:
                rainnc = rainnc[rain_idx]
                rainc = rainc[rain_idx]

        lat2d, lon2d = np.meshgrid(lats, lons, indexing="ij")

        def _collapse_max(arr: np.ndarray) -> np.ndarray:
            arr = np.asarray(arr, dtype=float)
            if arr.ndim >= 3:
                arr = np.nanmax(arr, axis=0)
            elif arr.ndim != 2:
                raise ValueError(f"Unexpected array shape {arr.shape} for NetCDF variable")
            if arr.ndim == 3:
                arr = arr[0]
            return arr

        ws_kmh = np.hypot(u10, v10) * 3.6
        ws_peak = _collapse_max(ws_kmh)
        total_rainfall = _collapse_max(rainnc + rainc)

        full_grid = pd.DataFrame({
            "lat": lat2d.ravel(),
            "lon": lon2d.ravel(),
            "ws_kmh": ws_peak.ravel(),
            "total_rainfall": total_rainfall.ravel(),
        })

        gdf_pts = gpd.GeoDataFrame(
            full_grid,
            geometry=gpd.points_from_xy(full_grid.lon, full_grid.lat),
            crs="EPSG:4326",
        )

        joined = gpd.sjoin(
            gdf_pts,
            gdf_upazila[["GEO_CODE", "UPAZILA_NAME", "geometry"]],
            how="inner",
            predicate="within",
        ).dropna(subset=["GEO_CODE"])

        aggregated = joined.groupby("GEO_CODE").agg(
            mean_ws_kmh=("ws_kmh", "mean"),
            peak_ws_kmh=("ws_kmh", "max"),
            max_total_rainfall=("total_rainfall", "max"),
        ).reset_index()

        admin_columns = [
            column for column in (
                "GEO_CODE", "UPAZILA_NAME", "DISTRICT_NAME", "TOTAL_POP", "TOTAL_HH", "HH_SIZE",
                "PUCCA_PCT", "SEMI_PUCCA_PCT", "KANCHA_PCT", "geometry",
                "MALE_POP", "FEMALE_POP", "AGE_0_4", "AGE_5_19", "AGE_60_PLUS",
            ) if column in gdf_upazila.columns
        ]
        gdf_all = gdf_upazila[admin_columns].merge(
            aggregated, on="GEO_CODE", how="left"
        )

        gdf_all = fill_missing_with_nearest_union(gdf_all, "mean_ws_kmh")
        gdf_all = fill_missing_with_nearest_union(gdf_all, "peak_ws_kmh")
        gdf_all = fill_missing_with_nearest_union(gdf_all, "max_total_rainfall")

        return gdf_all.drop(columns="geometry")
    finally:
        if temp_path and os.path.exists(temp_path):
            _safe_remove(temp_path)


def parse_storm_surge_upazila(nc_input: bytes | str | Path, gdf_upazila: gpd.GeoDataFrame) -> pd.DataFrame:
    """Aggregate storm surge at Upazila level for faster full-coverage maps.
    
    OPTIMIZED: Uses vectorized spatial join instead of per-polygon loops.
    """
    temp_path: str | None = None
    if isinstance(nc_input, (str, Path)):
        nc_path = str(nc_input)
    else:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".nc") as tmp:
            tmp.write(nc_input)
            nc_path = tmp.name
        temp_path = nc_path

    try:
        with _NETCDF_READ_LOCK, Dataset(nc_path, "r") as nc:
            if "z" not in nc.variables:
                raise KeyError("Storm surge file must contain 'z' variable")

            lats = nc["lat"][:]
            lons = nc["lon"][:]
            z_var = nc["z"]
            z = z_var[:].astype(float)

            fill_values: list[float] = []
            for attr in ("_FillValue", "missing_value"):
                if hasattr(z_var, attr):
                    fill_values.append(float(getattr(z_var, attr)))
            for fv in fill_values:
                z[z == fv] = np.nan
            z[z > 1e10] = np.nan
            z[z < -100] = np.nan

        minx, miny, maxx, maxy = gdf_upazila.total_bounds
        pad = 0.5
        lat_mask = (lats >= miny - pad) & (lats <= maxy + pad)
        lon_mask = (lons >= minx - pad) & (lons <= maxx + pad)

        lats = lats[lat_mask]
        lons = lons[lon_mask]
        if z.ndim == 3:
            z = z[:, lat_mask, :][:, :, lon_mask]
            z_max = np.nanmax(z, axis=0)
        elif z.ndim == 2:
            z = z[np.ix_(lat_mask, lon_mask)]
            z_max = z
        else:
            raise ValueError(f"Unexpected surge array shape {z.shape}")

        lat2d, lon2d = np.meshgrid(lats, lons, indexing="ij")

        df = pd.DataFrame({
            "lat": lat2d.ravel(),
            "lon": lon2d.ravel(),
            "storm_surge_m": z_max.ravel(),
        })
        gdf_pts = gpd.GeoDataFrame(
            df,
            geometry=gpd.points_from_xy(df.lon, df.lat),
            crs="EPSG:4326",
        )

        joined = gpd.sjoin(
            gdf_pts,
            gdf_upazila[["GEO_CODE", "UPAZILA_NAME", "geometry"]],
            how="inner",
            predicate="within",
        )

        aggregated = joined.groupby("GEO_CODE").agg(
            max_storm_surge_m=("storm_surge_m", "max"),
        ).reset_index()

        gdf_all = gdf_upazila[["GEO_CODE", "UPAZILA_NAME", "DISTRICT_NAME", "geometry"]].merge(
            aggregated, on="GEO_CODE", how="left"
        )
        gdf_all["max_storm_surge_m"] = gdf_all["max_storm_surge_m"].fillna(0.0)

        return gdf_all.drop(columns="geometry")
    finally:
        if temp_path and os.path.exists(temp_path):
            _safe_remove(temp_path)



def classify_risk(
    final_df: pd.DataFrame,
    df_percent: pd.DataFrame,
    df_number: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Merge on GEO_CODE. Uses Excel 'Union' for display; if missing, falls back
    to shapefile name (UNION_NAME) only when that column exists.
    """
    final_df = final_df.drop_duplicates(subset=["GEO_CODE"]).copy()
    df_percent = df_percent.drop_duplicates(subset=["GEO_CODE"]).copy()
    df_number = df_number.drop_duplicates(subset=["GEO_CODE"]).copy()
    df_percent["Kancha_Vulnerable"] = df_percent["Kancha"]

    risk_df = final_df.merge(
        df_percent[["GEO_CODE", "Union", "Kancha", "Semi-pucca", "Pucca", "Kancha_Vulnerable"]],
        on="GEO_CODE", how="left"
    ).merge(
        df_number[["GEO_CODE", "Kancha", "Semi-pucca", "Pucca"]]
        .rename(columns={
            "Kancha": "Kancha_num",
            "Semi-pucca": "Semi-pucca_num",
            "Pucca": "Pucca_num"
        }),
        on="GEO_CODE", how="left"
    )

    if "Union" not in risk_df.columns:
        risk_df["Union"] = np.nan
    if "UNION_NAME" in risk_df.columns:
        risk_df["Union"] = risk_df["Union"].fillna(risk_df["UNION_NAME"])
    if "DISTRICT_NAME" not in risk_df.columns:
        risk_df["DISTRICT_NAME"] = np.nan
    if "UPAZILA_NAME" in risk_df.columns:
        risk_df["Upazila"] = risk_df["UPAZILA_NAME"]
    else:
        risk_df["Upazila"] = np.nan

    classification_columns = [
        "GEO_CODE", "Union", "Upazila", "DISTRICT_NAME", "mean_ws_kmh", "peak_ws_kmh",
        "max_total_rainfall",
        "max_storm_surge_m",
        "Kancha", "Semi-pucca", "Pucca",
        "Kancha_num", "Semi-pucca_num", "Pucca_num"
    ]
    classification_columns.extend(
        column
        for column in (
            "BOUNDARY_GEO_CODE", "MUNICIPA_1", "CITY_NAME", "TOTAL_POP", "TOTAL_HH", "HH_SIZE",
            "MALE_POP", "FEMALE_POP", "AGE_0_4", "AGE_5_19", "AGE_60_PLUS",
        )
        if column in risk_df.columns
    )
    table_classification = risk_df[classification_columns].rename(columns={
        "mean_ws_kmh": "Wind Speed (km/h)",
        "peak_ws_kmh": "Peak Wind Speed (km/h)",
        "max_total_rainfall": "Total Rainfall (mm)",
        "max_storm_surge_m": "Storm Surge (m)",
        "Kancha": "Kancha (%)",
        "Semi-pucca": "Semi-pucca (%)",
        "Pucca": "Pucca (%)",
        "DISTRICT_NAME": "District",
        "MUNICIPA_1": "Municipality",
        "CITY_NAME": "City Corporation",
        "TOTAL_POP": "BBS Population",
        "TOTAL_HH": "BBS Households",
        "HH_SIZE": "BBS Household Size",
        "MALE_POP": "BBS Male Population",
        "FEMALE_POP": "BBS Female Population",
        "AGE_0_4": "BBS Age 0-4",
        "AGE_5_19": "BBS Age 5-19",
        "AGE_60_PLUS": "BBS Age 60+",
        "BOUNDARY_GEO_CODE": "Boundary GEO_CODE",
    })

    table_classification = table_classification.drop_duplicates(subset=["GEO_CODE"])
    risk_df = risk_df.drop_duplicates(subset=["GEO_CODE"])

    return risk_df, table_classification


def build_damage_table(table_classification: pd.DataFrame, damage_model: str = "ccm") -> pd.DataFrame:
    """
    Given the classification table, compute damage expectations and evacuation
    decisions for each housing type in each union.

    Parameters
    ----------
    table_classification : pandas.DataFrame
        Classification table containing union names, wind speed and rainfall.

    Returns
    -------
    pandas.DataFrame
        A table summarising damage descriptions and evacuation recommendations
        for each housing type per union.
    """
    model_normalized = (damage_model or "ccm").lower()
    damage_types = CCM_DAMAGE_TYPES if model_normalized == "ccm" else ["Kancha", "Semi-pucca", "Pucca"]
    damage_records: list[dict] = []
    for _, row in table_classification.iterrows():
        record: dict[str, object] = {
            "GEO_CODE": row.get("GEO_CODE"),
            "Union": row["Union"],
            "District": row.get("District", ""),
            "Upazila": row.get("Upazila", ""),
            "Wind Speed (km/h)": row["Wind Speed (km/h)"],
            "Total Rainfall (mm)": row["Total Rainfall (mm)"],
            "Storm Surge (m)": row.get("Storm Surge (m)"),
        }
        if model_normalized == "ccm":
            severity_code = ccm_damage_code(
                _safe_float(row.get("Wind Speed (km/h)")),
                _safe_float(row.get("Storm Surge (m)")),
            )
            severity_def = CCM_DAMAGE_CLASS_MAP.get(severity_code, CCM_DAMAGE_CLASS_MAP[1])
            record["CCM Class"] = severity_code
            for typ in damage_types:
                status = severity_def.get(typ, "No")
                record[f"{typ} Damage"] = format_ccm_damage(status)
                record[f"{typ} Evacuate"] = "Yes" if status.lower() == "full" else "No"
        else:
            for typ in damage_types:
                dmg, ev = get_damage(row["Wind Speed (km/h)"], typ)
                record[f"{typ} Damage"] = dmg
                record[f"{typ} Evacuate"] = "Yes" if ev else "No"
        damage_records.append(record)

    table_damage = pd.DataFrame(damage_records)
    if table_damage.empty:
        return table_damage
    table_damage["SortSeverity"] = table_damage.apply(row_severity, axis=1)
    table_damage = (
        table_damage
        .sort_values(["SortSeverity"])
        .drop(columns=["SortSeverity"])
        .reset_index(drop=True)
    )
    return table_damage



def build_rainfall_evac_table(table_classification: pd.DataFrame) -> pd.DataFrame:
    """
    Determine which housing types need to evacuate based on rainfall triggers.

    Parameters
    ----------
    table_classification : pandas.DataFrame
        Classification table used to look up total rainfall per union.

    Returns
    -------
    pandas.DataFrame
        Table containing unions, their rainfall and the housing types
        requiring evacuation.
    """
    rainfall_evac_records: list[dict] = []
    for _, row in table_classification.iterrows():
        union_name = row["Union"]
        rainfall = row["Total Rainfall (mm)"]
        evac_types = rainfall_evacuation_actions(rainfall)
        for types in evac_types:
            rainfall_evac_records.append({
                "GEO_CODE": row.get("GEO_CODE"),
                "Union": union_name,
                "Rainfall (mm/day)": rainfall,
                "Evacuate House Types": types
            })
    return pd.DataFrame(rainfall_evac_records)


def export_gis_map_excel(
    risk_df: pd.DataFrame,
    upazila_df: pd.DataFrame,
    table_classification: pd.DataFrame,
    table_damage: pd.DataFrame,
    gdf_union: gpd.GeoDataFrame,
    gdf_upazila: gpd.GeoDataFrame,
    output_path: str | Path,
) -> Path:
    """
    Export GIS map data to a single Excel file.
    
    Contains all data needed to regenerate maps in GIS software:
    - GEO_CODE, Union, Upazila, District, affected population, Risk
    - Average Wind Speed (model input), Maximum Wind Speed (visualization),
      Total Rainfall (mm), Storm Surge (m)
    - CCM Class, Kancha Damage, Semi-pucca Damage, Pucca Damage
    - centroid_lon, centroid_lat
    
    Parameters
    ----------
    risk_df : pd.DataFrame
        Risk classification data with GEO_CODE
    upazila_df : pd.DataFrame
        Upazila-level weather data
    table_classification : pd.DataFrame
        Full classification table
    table_damage : pd.DataFrame
        Damage table with CCM Class and damage columns
    gdf_union : gpd.GeoDataFrame
        Union shapefile geodataframe
    gdf_upazila : gpd.GeoDataFrame
        Upazila shapefile geodataframe
    output_path : str | Path
        Path to save the Excel file
    
    Returns
    -------
    Path
        Path to the created Excel file
    """
    output_path = Path(output_path)
    
    gis_data = table_classification.copy()
    
    if not table_damage.empty:
        damage_cols_to_add = ["GEO_CODE"]
        if "CCM Class" in table_damage.columns:
            damage_cols_to_add.append("CCM Class")
        for col in ["Kancha Damage", "Semi-pucca Damage", "Pucca Damage"]:
            if col in table_damage.columns:
                damage_cols_to_add.append(col)
        
        if len(damage_cols_to_add) > 1:
            damage_subset = table_damage[damage_cols_to_add].drop_duplicates(subset=["GEO_CODE"])
            gis_data = gis_data.merge(damage_subset, on="GEO_CODE", how="left")
    
    final_cols = [
        "GEO_CODE", "Union", "Upazila", "District",
        "Affected Population", "Total Population", "Affected Population (%)", "Risk",
        "Average Wind Speed (km/h) [model]", "Maximum Wind Speed (km/h) [visualization]",
        "Total Rainfall (mm)", "Storm Surge (m)",
        "CCM Class", "Kancha Damage", "Semi-pucca Damage", "Pucca Damage",
        "centroid_lon", "centroid_lat"
    ]
    
    if "GEO_CODE" in gdf_union.columns:
        gdf_union_temp = gdf_union.copy()
        gdf_union_temp["centroid_lon"] = gdf_union_temp.geometry.centroid.x
        gdf_union_temp["centroid_lat"] = gdf_union_temp.geometry.centroid.y
        coords_union = gdf_union_temp[["GEO_CODE", "centroid_lon", "centroid_lat"]]
        gis_data = gis_data.merge(coords_union, on="GEO_CODE", how="left")
    
    available_cols = [c for c in final_cols if c in gis_data.columns]
    gis_data = gis_data[available_cols].copy()
    
    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        gis_data.to_excel(writer, index=False, sheet_name="GIS_Map_Data")
        
        wb = writer.book
        ws = writer.sheets["GIS_Map_Data"]
        
        if "Risk" in gis_data.columns:
            rank_idx = gis_data.columns.get_loc("Risk")
            for i, val in enumerate(gis_data["Risk"]):
                cell_val = "" if pd.isna(val) or str(val) == "nan" else str(val)
                if cell_val:
                    bg_color = risk_color(cell_val)
                    if bg_color:
                        fmt = wb.add_format({"bg_color": bg_color})
                        ws.write(i + 1, rank_idx, cell_val, fmt)
        
        for col in ["Kancha Damage", "Semi-pucca Damage", "Pucca Damage"]:
            if col in gis_data.columns:
                col_idx = gis_data.columns.get_loc(col)
                for i, val in enumerate(gis_data[col]):
                    cell_val = "" if pd.isna(val) or str(val) == "nan" else str(val)
                    if cell_val:
                        bg_color = damage_color(cell_val)
                        if bg_color:
                            fmt_dict = {"bg_color": bg_color}
                            if needs_white_font(bg_color):
                                fmt_dict["font_color"] = "white"
                            fmt = wb.add_format(fmt_dict)
                            ws.write(i + 1, col_idx, cell_val, fmt)
    
    return output_path



def export_classification_excel(
    table_classification: pd.DataFrame,
    output_path: str | Path,
) -> Path:
    """
    Export the risk classification table to an Excel file with coloured risk
    categories.

    Parameters
    ----------
    table_classification : pandas.DataFrame
        DataFrame containing classification results.

    Returns
    -------
    str
        Path to the temporary Excel file.
    """
    output_path = Path(output_path)
    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        t1 = table_classification.copy()
        t1["Risk"] = t1["Risk"].astype(str).replace("nan", "")
        t1.to_excel(writer, index=False, sheet_name="RiskClassification")
        wb = writer.book
        ws = writer.sheets["RiskClassification"]
        rank_idx = t1.columns.get_loc("Risk")
        for i, val in enumerate(t1["Risk"]):
            cell_val = "" if pd.isna(val) or val == "nan" else val
            if cell_val:
                bg_color = risk_color(cell_val)
                if bg_color:
                    fmt_dict = {"bg_color": bg_color}
                    fmt = wb.add_format(fmt_dict)
                    ws.write(i + 1, rank_idx, cell_val, fmt)
                else:
                    ws.write(i + 1, rank_idx, cell_val)
            else:
                ws.write(i + 1, rank_idx, "")
    return output_path

def export_damage_excel(
    table_damage: pd.DataFrame,
    output_path: str | Path,
) -> Path:
    """
    Export the housing damage table to an Excel file.
    - Keeps damage cells colorized.
    """
    output_path = Path(output_path)
    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        t2 = table_damage.copy()

        for col in t2.columns:
            if "Damage" in col:
                t2[col] = t2[col].astype(str).replace("nan", "")

        t2.to_excel(writer, index=False, sheet_name="HousingDanger")

        wb = writer.book
        ws = writer.sheets["HousingDanger"]
        for col in t2.columns:
            if "Damage" in col:
                col_idx = t2.columns.get_loc(col)
                for i, val in enumerate(t2[col]):
                    cell_val = "" if pd.isna(val) or val == "nan" else val
                    if cell_val:
                        bg_color = damage_color(cell_val)
                        if bg_color:
                            fmt_dict = {"bg_color": bg_color}
                            if needs_white_font(bg_color):
                                fmt_dict["font_color"] = "white"
                            fmt = wb.add_format(fmt_dict)
                            ws.write(i + 1, col_idx, cell_val, fmt)
                        else:
                            ws.write(i + 1, col_idx, cell_val)
                    else:
                        ws.write(i + 1, col_idx, "")

    return output_path



def export_rainfall_evac_excel(
    table_rainfall_evac: pd.DataFrame,
    output_path: str | Path,
) -> Path:
    """
    Export the rainfall evacuation triggers table to an Excel file.

    Parameters
    ----------
    table_rainfall_evac : pandas.DataFrame
        Table produced by ``build_rainfall_evac_table``.

    Returns
    -------
    str
        Path to the temporary Excel file.
    """
    output_path = Path(output_path)
    table_rainfall_evac.to_excel(output_path, index=False)
    return output_path


def build_guideline(
    table_classification: pd.DataFrame,
    table_damage: pd.DataFrame,
    table_rainfall_evac: pd.DataFrame,
    overall_damage_types: list[str],
    class_info: dict,
    polished: bool = True
) -> str:
    """
    Construct a Markdown guideline in Bengali based on classification,
    damage and rainfall analyses. Optionally polish the language via LLM.

    Parameters
    ----------
    table_classification : pandas.DataFrame
        Classification table.
    table_damage : pandas.DataFrame
        Damage table.
    table_rainfall_evac : pandas.DataFrame
        Rainfall evacuation table.
    overall_damage_types : list of str
        List of housing types with non‑minor damage across the dataset.
    class_info : dict
        Dictionary summarising per‑risk‑class maximum wind speeds, damaged
        structures and evacuation recommendations.
    polished : bool, default True
        If True the template will be sent through the LLM for polishing.

    Returns
    -------
    str
        The final guideline in Markdown format.
    """
    rainfall_top = table_classification["Total Rainfall (mm)"].max()
    rainfall_top_union = table_classification.loc[
        table_classification["Total Rainfall (mm)"].idxmax(), "Union"
    ]
    if len(table_rainfall_evac) > 0:
        grouped = table_rainfall_evac.groupby("Evacuate House Types")
        evac_md_parts = []
        for types, group in grouped:
            unions = ", ".join(
                str(x) for x in group["Union"] if pd.notnull(x) and str(x).lower() != "nan"
            )
            evac_md_parts.append(f"- **{types}**: {unions}")
        evac_md = "\n".join(evac_md_parts)
    else:
        evac_md = "None"

    risk_classes = ["Very High", "High", "Medium", "Low", "Very Low"]
    risk_class_block = ""
    for rc in risk_classes:
        if rc not in class_info:
            continue
        wind = class_info[rc]["max_wind"]
        dmglist = "; ".join(class_info[rc]["damages"])
        evaclist = ", ".join(class_info[rc]["evacuate"]) if class_info[rc]["evacuate"] else "None"
        risk_class_block += f"\n- **{rc}**: Max Wind: {wind:.1f} km/h; Damaged structures: {dmglist}; Evacuate: {evaclist}"

    top5 = table_classification.sort_values(
        "Affected Population (%)", ascending=False, na_position="last"
    ).head(5)
    top5_list = ", ".join(top5["Union"].astype(str).tolist())
    max_speed = table_classification["Wind Speed (km/h)"].max()
    max_speed_union = table_classification.loc[
        table_classification["Wind Speed (km/h)"].idxmax(), "Union"
    ]

    pre_cyclone = "\n".join([f"**{typ}**:\n{get_preparedness(typ)}" for typ in overall_damage_types])
    post_cyclone = "\n".join([f"**{typ}**:\n{get_post_materials(typ)}" for typ in overall_damage_types])

    template = f"""

এই নির্দেশিকাটি প্রাক্কলিত ঘূর্ণিঝড়ের বাতাসের সর্বোচ্চ গতির ও অতিবর্ষণের উপর ভিত্তি করে প্রস্তুত করা হয়েছে এবং বিশেষভাবে বিভিন্ন ইউনিয়নের আবাসন কাঠামোর ঝুঁকি ও সম্ভাব্য ক্ষয়ক্ষতি বিশ্লেষণ করেছে।
এর লক্ষ্য হল ঝুঁকিপূর্ণ বাড়ির ধরন ও অঞ্চলে জীবন ও সম্পদের ক্ষয়ক্ষতি কমাতে দ্রুত এবং কার্যকর ব্যবস্থা গ্রহণ নিশ্চিত করা।

- **ক্ষতিগ্রস্ত জনসংখ্যার শতাংশে সর্বোচ্চ ঝুঁকি:** {top5_list}
- **সর্বোচ্চ বাতাসের গতি:** {max_speed:.1f} কিমি/ঘণ্টা ({max_speed_union} এ)

{risk_class_block}

- **সর্বোচ্চ বৃষ্টিপাত:** {rainfall_top:.1f} mm/day ({rainfall_top_union} এ)
- **বৃষ্টিপাতে আশ্রয় নেওয়া আবশ্যক বাড়ির ধরন ও ইউনিয়ন:**  
{evac_md}

প্রধানত নিচের ধরনের বাড়িগুলো ক্ষতির মুখোমুখি হতে পারে। সংশ্লিষ্ট বসবাসকারীদের বিশেষ সতর্ক থাকতে হবে।
- {', '.join(overall_damage_types)}

{pre_cyclone}

{post_cyclone}

   - ঘূর্ণিঝড়ের পূর্বাভাস নিয়মিত শুনুন: রেডিও, টেলিভিশন, এবং সরকারি ওয়েবসাইটে নজর রাখুন।
   - জরুরী অবস্থার জন্য শুকনো খাবার, পানি, ঔষধ, টর্চলাইট, রেডিও এবং অন্যান্য প্রয়োজনীয় সামগ্রী প্রস্তুত রাখুন।
   - গুরুত্বপূর্ণ কাগজপত্র এবং মূল্যবান জিনিসপত্র নিরাপদ স্থানে রাখুন।
   - আপনার এলাকার আশ্রয়কেন্দ্রের ঠিকানা জেনে রাখুন।
   - পারিবারিক দুর্যোগ পরিকল্পনা তৈরি করুন এবং পরিবারের সদস্যদের সাথে আলোচনা করুন।
   - বিদ্যুৎ এবং গ্যাসের লাইন বন্ধ করার নিয়মাবলী জেনে রাখুন।
"""
    return polish_guideline(template, polished=polished)

def fill_map_gaps(
    gdf_map: gpd.GeoDataFrame,
    column: str,
    missing_label: str,
    severity_order: Sequence[str] = (),
    max_passes: int = 4,
) -> tuple[gpd.GeoDataFrame, int]:
    """Replace `missing_label` polygons with the mode of their neighbours.

    Final safety net at the render layer: whatever the upstream table did or
    did not cover, a choropleth should not show grey holes punched through a
    continuous surface. Adjacency comes from the polygons actually being
    drawn, so it also catches boundaries that never had a row in the metric
    table at all. Ties break toward the more severe class when a severity
    order is given, so a hole between two classes is never filled
    optimistically. Polygons with no classified neighbour after several
    passes (a genuinely isolated island) keep the missing label.
    """
    if gdf_map is None or gdf_map.empty or column not in gdf_map.columns:
        return gdf_map, 0

    values = gdf_map[column].astype(str).tolist()
    missing = [i for i, v in enumerate(values) if v == missing_label]
    if not missing:
        return gdf_map, 0

    geometry = gdf_map.geometry
    valid = geometry.notna() & ~geometry.is_empty
    if not valid.any():
        return gdf_map, 0
    left, right = geometry[valid].sindex.query(geometry[valid], predicate="intersects")
    positions = [i for i, ok in enumerate(valid.tolist()) if ok]
    adjacency: dict[int, list[int]] = {i: [] for i in positions}
    for a, b in zip(left, right):
        if a != b:
            adjacency[positions[a]].append(positions[b])

    rank = {name: i for i, name in enumerate(severity_order)}
    filled = 0
    for _ in range(max_passes):
        pending = [i for i in missing if values[i] == missing_label]
        if not pending:
            break
        resolved: dict[int, str] = {}
        for i in pending:
            neighbours = [values[n] for n in adjacency.get(i, []) if values[n] != missing_label]
            if not neighbours:
                continue
            counts = Counter(neighbours)
            top = max(counts.values())
            tied = [v for v, c in counts.items() if c == top]
            resolved[i] = max(tied, key=lambda v: rank.get(v, -1))
        if not resolved:
            break
        for i, value in resolved.items():
            values[i] = value
        filled += len(resolved)

    gdf_map = gdf_map.copy()
    gdf_map[column] = values
    return gdf_map, filled


def make_risk_map(risk_df: pd.DataFrame, gdf_union: gpd.GeoDataFrame, output_path: str | Path) -> Path:
    risk_palette = {
        "Very High": "#d73027",
        "High": "#fc8d59",
        "Medium": "#fee08b",
        "Low": "#91cf60",
        "Very Low": "#1a9850",
        "No Data": "#d9d9d9",
    }

    map_values = risk_df.copy()
    if "Boundary GEO_CODE" in map_values.columns:
        map_values["MAP_GEO_CODE"] = map_values["Boundary GEO_CODE"].fillna(map_values["GEO_CODE"])
    else:
        map_values["MAP_GEO_CODE"] = map_values["GEO_CODE"]
    gdf_map = gdf_union.merge(
        map_values[["MAP_GEO_CODE", "Risk"]].rename(columns={"MAP_GEO_CODE": "GEO_CODE"}),
        on="GEO_CODE", how="left",
    )
    gdf_map["Risk"] = (
        gdf_map["Risk"].astype(str).replace("nan", "No Data").replace("None", "No Data").replace("", "No Data")
    )
    gdf_map, _filled = fill_map_gaps(gdf_map, "Risk", "No Data", severity_order=_RISK_ORDER)
    if _filled:
        print(f"[gap-fill] risk map: {_filled} polygons filled from neighbours", flush=True)

    gdf_map = gdf_map[["geometry", "UNION_NAME", "Risk"]]

    m = folium.Map([23.7, 90.4], zoom_start=7)
    folium.GeoJson(
        gdf_map,
        style_function=lambda feat: {
            "fillColor": risk_palette.get(feat["properties"].get("Risk"), "#d9d9d9"),
            "color": "black", "weight": 0.3, "fillOpacity": 0.7
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["UNION_NAME", "Risk"],
            aliases=["Union", "Risk (affected population %)"],
            localize=True
        )
    ).add_to(m)

    legend_html = """
    <div style="
        position: fixed; bottom: 30px; left: 30px;
        width: 170px; background: white; padding: 10px;
        border: 2px solid grey; z-index:9999;
    ">
      <h4 style="margin:0 0 5px">Risk Category</h4>
      {}
    </div>
    """.format(
        "".join(
            f'<i style="background:{col};width:12px;height:12px;display:inline-block;margin-right:6px;"></i>{cat}<br>'
            for cat, col in risk_palette.items()
            if cat != "No Data" or (gdf_map["Risk"] == "No Data").any()
        )
    )
    m.get_root().html.add_child(Element(legend_html))
    output_path = Path(output_path)
    m.save(str(output_path))
    return output_path




IMD_WIND_CLASSES: list[dict] = [
    {"name": "Low-pressure",              "lo": None, "hi": 31,   "color": "#b3e5fc"},
    {"name": "Depression",                "lo": 32,   "hi": 49,   "color": "#81d4fa"},
    {"name": "Deep Depression",           "lo": 50,   "hi": 61,   "color": "#4fc3f7"},
    {"name": "Cyclonic Storm",            "lo": 62,   "hi": 88,   "color": "#ffeb3b"},
    {"name": "Severe Cyclonic",           "lo": 89,   "hi": 117,  "color": "#ff9800"},
    {"name": "Very Severe Cyclonic",      "lo": 118,  "hi": 166,  "color": "#f44336"},
    {"name": "Extremely Severe Cyclonic", "lo": 167,  "hi": 221,  "color": "#b71c1c"},
    {"name": "Super Cyclonic",            "lo": 222,  "hi": None, "color": "#4a148c"},
]

IMD_NO_DATA_LABEL = "No Data"
IMD_NO_DATA_COLOR = "#e0e0e0"


def _imd_range_text(cls: dict) -> str:
    """"≤31 km/h" / "32-49 km/h" / "≥222 km/h" for one class."""
    if cls["lo"] is None:
        return f"≤{cls['hi']} km/h"
    if cls["hi"] is None:
        return f"≥{cls['lo']} km/h"
    return f"{cls['lo']}-{cls['hi']} km/h"


def imd_wind_class_index(wind_speed_kmh: float) -> int | None:
    """Index into IMD_WIND_CLASSES, or None when there is no usable value."""
    try:
        if wind_speed_kmh is None or pd.isna(wind_speed_kmh) or wind_speed_kmh < 0:
            return None
    except (TypeError, ValueError):
        return None
    for i, cls in enumerate(IMD_WIND_CLASSES):
        if cls["hi"] is None or wind_speed_kmh <= cls["hi"]:
            return i
    return len(IMD_WIND_CLASSES) - 1


def get_imd_wind_category(wind_speed_kmh: float) -> str:
    """Classify wind speed according to the IMD scale.

    Returns the full label with its range, e.g. "Cyclonic Storm (62-88 km/h)".
    """
    idx = imd_wind_class_index(wind_speed_kmh)
    if idx is None:
        return IMD_NO_DATA_LABEL
    cls = IMD_WIND_CLASSES[idx]
    return f"{cls['name']} ({_imd_range_text(cls)})"


def imd_legend_label(cls: dict) -> str:
    """Compact form for map legends: "Cyclonic Storm 62-88"."""
    if cls["lo"] is None:
        return f"{cls['name']} ≤{cls['hi']}"
    if cls["hi"] is None:
        return f"{cls['name']} ≥{cls['lo']}"
    return f"{cls['name']} {cls['lo']}-{cls['hi']}"


IMD_WIND_PALETTE = {
    get_imd_wind_category(cls["hi"] if cls["hi"] is not None else cls["lo"]): cls["color"]
    for cls in IMD_WIND_CLASSES
}
IMD_WIND_PALETTE[IMD_NO_DATA_LABEL] = IMD_NO_DATA_COLOR


def make_wind_intensity_map(
    upazila_df: pd.DataFrame,
    gdf_upazila: gpd.GeoDataFrame,
    output_path: str | Path
) -> Path:
    """Create a choropleth map showing wind speed intensity based on IMD scale.
    
    Uses Upazila-level data for faster rendering (fewer polygons than Union).
    """
    
    wind_palette = IMD_WIND_PALETTE
    
    wind_col = "peak_ws_kmh"
    if wind_col not in upazila_df.columns:
        raise ValueError(f"{wind_col} column not found in Upazila data; cannot build wind intensity map")
    
    data_with_category = upazila_df.copy()
    data_with_category["Wind Intensity"] = data_with_category[wind_col].apply(get_imd_wind_category)
    
    gdf_map = gdf_upazila.merge(
        data_with_category[["GEO_CODE", wind_col, "Wind Intensity"]],
        on="GEO_CODE",
        how="left"
    )
    
    gdf_map["Wind Intensity"] = gdf_map["Wind Intensity"].fillna("No Data")
    gdf_map, _filled = fill_map_gaps(
        gdf_map, "Wind Intensity", "No Data",
        severity_order=[get_imd_wind_category(c["hi"] if c["hi"] is not None else c["lo"]) for c in IMD_WIND_CLASSES],
    )
    if _filled:
        print(f"[gap-fill] wind map: {_filled} polygons filled from neighbours", flush=True)

    gdf_map = gdf_map[["geometry", "UPAZILA_NAME", wind_col, "Wind Intensity"]]

    m = folium.Map([23.7, 90.4], zoom_start=7)
    folium.GeoJson(
        gdf_map,
        style_function=lambda feat: {
            "fillColor": wind_palette.get(feat["properties"].get("Wind Intensity"), "#e0e0e0"),
            "color": "black",
            "weight": 0.3,
            "fillOpacity": 0.7,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["UPAZILA_NAME", wind_col, "Wind Intensity"],
            aliases=["Upazila", "Maximum Wind Speed (km/h)", "IMD Category"],
            localize=True,
        ),
    ).add_to(m)
    
    legend_html = """
    <div style="
        position: fixed; bottom: 30px; left: 30px;
        width: 260px; background: white; padding: 10px;
        border: 2px solid grey; z-index:9999; font-size: 11px;
    ">
      <h4 style="margin:0 0 5px">Wind Intensity (IMD Scale)</h4>
      {}
    </div>
    """.format(
        "".join(
            f'<i style="background:{col};width:12px;height:12px;display:inline-block;margin-right:6px;"></i>{cat}<br>'
            for cat, col in wind_palette.items()
            if cat != "No Data" or (gdf_map["Wind Intensity"] == "No Data").any()
        )
    )
    m.get_root().html.add_child(Element(legend_html))
    output_path = Path(output_path)
    m.save(str(output_path))
    return output_path



def get_storm_surge_category(surge_m: float) -> str:
    """Classify storm surge height into risk categories."""
    if pd.isna(surge_m) or surge_m < 0:
        return "No Data"
    if surge_m <= 1.0:
        return "Very Low (≤1m)"
    if surge_m <= 2.0:
        return "Low (1-2m)"
    if surge_m <= 3.0:
        return "Moderate (2-3m)"
    if surge_m <= 4.0:
        return "High (3-4m)"
    if surge_m <= 5.0:
        return "Very High (4-5m)"
    return "Extreme (>5m)"


def make_storm_surge_map(
    upazila_df: pd.DataFrame,
    gdf_upazila: gpd.GeoDataFrame,
    output_path: str | Path
) -> Path:
    """Create a choropleth map showing storm surge risk levels.
    
    Uses Upazila-level data for faster rendering (fewer polygons than Union).
    """
    
    surge_palette = {
        "Very Low (≤1m)": "#a5d6a7",     # Light green
        "Low (1-2m)": "#fff59d",          # Light yellow
        "Moderate (2-3m)": "#ffcc80",     # Light orange
        "High (3-4m)": "#ff8a65",         # Orange
        "Very High (4-5m)": "#e57373",    # Light red
        "Extreme (>5m)": "#b71c1c",       # Dark red
        "No Data": "#e0e0e0",             # Grey
    }
    
    surge_col = "max_storm_surge_m"
    if surge_col not in upazila_df.columns:
        raise ValueError(f"{surge_col} column not found in Upazila data; cannot build storm surge map")
    
    data_with_category = upazila_df.copy()
    data_with_category["Surge Category"] = data_with_category[surge_col].apply(get_storm_surge_category)
    
    gdf_map = gdf_upazila.merge(
        data_with_category[["GEO_CODE", surge_col, "Surge Category"]],
        on="GEO_CODE",
        how="left"
    )
    
    gdf_map["Surge Category"] = gdf_map["Surge Category"].fillna("No Data")
    gdf_map, _filled = fill_map_gaps(gdf_map, "Surge Category", "No Data", severity_order=list(surge_palette))
    if _filled:
        print(f"[gap-fill] surge map: {_filled} polygons filled from neighbours", flush=True)

    gdf_map = gdf_map[["geometry", "UPAZILA_NAME", surge_col, "Surge Category"]]

    m = folium.Map([23.7, 90.4], zoom_start=7)
    folium.GeoJson(
        gdf_map,
        style_function=lambda feat: {
            "fillColor": surge_palette.get(feat["properties"].get("Surge Category"), "#e0e0e0"),
            "color": "black",
            "weight": 0.3,
            "fillOpacity": 0.7,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["UPAZILA_NAME", surge_col, "Surge Category"],
            aliases=["Upazila", "Storm Surge (m)", "Risk Level"],
            localize=True,
        ),
    ).add_to(m)
    
    legend_html = """
    <div style="
        position: fixed; bottom: 30px; left: 30px;
        width: 180px; background: white; padding: 10px;
        border: 2px solid grey; z-index:9999;
    ">
      <h4 style="margin:0 0 5px">Storm Surge Risk</h4>
      {}
    </div>
    """.format(
        "".join(
            f'<i style="background:{col};width:12px;height:12px;display:inline-block;margin-right:6px;"></i>{cat}<br>'
            for cat, col in surge_palette.items()
            if cat != "No Data" or (gdf_map["Surge Category"] == "No Data").any()
        )
    )
    m.get_root().html.add_child(Element(legend_html))
    output_path = Path(output_path)
    m.save(str(output_path))
    return output_path



def get_rainfall_category(rainfall_mm: float) -> str:
    """Classify rainfall into risk categories based on daily accumulation."""
    if pd.isna(rainfall_mm) or rainfall_mm < 0:
        return "No Data"
    if rainfall_mm <= 50:
        return "Low (≤50mm)"
    if rainfall_mm <= 100:
        return "Moderate (50-100mm)"
    if rainfall_mm <= 200:
        return "High (100-200mm)"
    if rainfall_mm <= 400:
        return "Very High (200-400mm)"
    return "Extreme (>400mm)"


def make_rainfall_risk_map(
    upazila_df: pd.DataFrame,
    gdf_upazila: gpd.GeoDataFrame,
    output_path: str | Path
) -> Path:
    """Create a choropleth map showing rainfall risk levels.
    
    Uses Upazila-level data for faster rendering (fewer polygons than Union).
    """
    
    rainfall_palette = {
        "Low (≤50mm)": "#c8e6c9",          # Light green
        "Moderate (50-100mm)": "#81d4fa",  # Light blue
        "High (100-200mm)": "#4fc3f7",     # Blue
        "Very High (200-400mm)": "#7e57c2", # Purple
        "Extreme (>400mm)": "#4a148c",     # Dark purple
        "No Data": "#e0e0e0",              # Grey
    }
    
    rainfall_col = "max_total_rainfall"
    if rainfall_col not in upazila_df.columns:
        raise ValueError(f"{rainfall_col} column not found in Upazila data; cannot build rainfall risk map")
    
    data_with_category = upazila_df.copy()
    data_with_category["Rainfall Category"] = data_with_category[rainfall_col].apply(get_rainfall_category)
    
    gdf_map = gdf_upazila.merge(
        data_with_category[["GEO_CODE", rainfall_col, "Rainfall Category"]],
        on="GEO_CODE",
        how="left"
    )
    
    gdf_map["Rainfall Category"] = gdf_map["Rainfall Category"].fillna("No Data")
    gdf_map, _filled = fill_map_gaps(gdf_map, "Rainfall Category", "No Data", severity_order=list(rainfall_palette))
    if _filled:
        print(f"[gap-fill] rainfall map: {_filled} polygons filled from neighbours", flush=True)

    gdf_map = gdf_map[["geometry", "UPAZILA_NAME", rainfall_col, "Rainfall Category"]]

    m = folium.Map([23.7, 90.4], zoom_start=7)
    folium.GeoJson(
        gdf_map,
        style_function=lambda feat: {
            "fillColor": rainfall_palette.get(feat["properties"].get("Rainfall Category"), "#e0e0e0"),
            "color": "black",
            "weight": 0.3,
            "fillOpacity": 0.7,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["UPAZILA_NAME", rainfall_col, "Rainfall Category"],
            aliases=["Upazila", "Total Rainfall (mm)", "Risk Level"],
            localize=True,
        ),
    ).add_to(m)
    
    legend_html = """
    <div style="
        position: fixed; bottom: 30px; left: 30px;
        width: 180px; background: white; padding: 10px;
        border: 2px solid grey; z-index:9999;
    ">
      <h4 style="margin:0 0 5px">Rainfall Risk</h4>
      {}
    </div>
    """.format(
        "".join(
            f'<i style="background:{col};width:12px;height:12px;display:inline-block;margin-right:6px;"></i>{cat}<br>'
            for cat, col in rainfall_palette.items()
            if cat != "No Data" or (gdf_map["Rainfall Category"] == "No Data").any()
        )
    )
    m.get_root().html.add_child(Element(legend_html))
    output_path = Path(output_path)
    m.save(str(output_path))
    return output_path



def rainfall_evacuation_actions(rainfall):
    result = []
    for level, types in rainfall_triggers:
        if rainfall >= level:
            result.append(types)
    return result


def summarise_damage_and_risk(table_damage: pd.DataFrame) -> tuple[list[str], dict]:
    """
    Identify housing types that experience non-minor damage anywhere and
    summarise key statistics for each risk class.

    Parameters
    ----------
    table_damage : pandas.DataFrame
        Damage table produced by ``build_damage_table``.

    Returns
    -------
    tuple
        (overall_damaged_types, class_info) where
        overall_damaged_types : list of str
            List of housing types with at least one non-minor damage case.
        class_info : dict
            Dictionary keyed by risk category containing maximum wind,
            damaged structures and evacuation list for that category.
    """
    damage_cols = [col for col in table_damage.columns if col.endswith(" Damage")]
    damage_types = [col.replace(" Damage", "") for col in damage_cols]
    overall_damaged_types: list[str] = []
    for typ in damage_types:
        col = f"{typ} Damage"
        if col not in table_damage.columns:
            continue
        series = table_damage[col].astype(str).str.lower()
        if series.empty:
            continue
        only_minor = series.str.contains("minor", na=False).all()
        only_blank = series.str.strip().eq("").all()
        if not only_minor and not only_blank:
            overall_damaged_types.append(typ)

    risk_classes = ["Very High", "High", "Medium", "Low", "Very Low"]
    class_info: dict[str, dict] = {}
    for rc in risk_classes:
        mask = table_damage["Risk"].astype(str) == rc
        subset = table_damage[mask]
        if subset.empty:
            continue
        max_wind = subset["Wind Speed (km/h)"].max()
        damages: list[str] = []
        to_evacuate: list[str] = []
        for typ in damage_types:
            dmg_col = f"{typ} Damage"
            evac_col = f"{typ} Evacuate"
            if dmg_col not in subset.columns:
                continue
            top_row = subset.loc[subset["Wind Speed (km/h)"].idxmax()]
            dmg = _safe_str(top_row.get(dmg_col, ""))
            ev = _safe_str(top_row.get(evac_col, "No"))
            dmg_lower = dmg.lower()
            if dmg and "minor" not in dmg_lower:
                damages.append(f"{typ}: {dmg}")
            if ev.lower() == "yes":
                to_evacuate.append(typ)
        class_info[rc] = {
            "max_wind": max_wind,
            "damages": damages,
            "evacuate": to_evacuate
        }
    return overall_damaged_types, class_info


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_percent(value: object) -> float | None:
    """Like ``_safe_float`` but rejects values outside a valid 0-100% range.

    A small fraction of rows in union_bbs.csv have corrupted
    Percent_*_House columns (e.g. 4440% — apparently duplicated from the
    neighbouring count column at source). Rather than display a nonsensical
    percentage in a guideline/report, treat those as missing data so
    downstream renders "N/A" instead of fabricating a plausible-looking but
    wrong figure.
    """
    parsed = _safe_float(value)
    if parsed is None:
        return None
    if parsed < 0 or parsed > 100.5:
        return None
    return parsed


def _safe_str(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, pd.Series):
        if value.empty:
            return ""
        value = value.iloc[0]
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if value is None:
        return ""
    return str(value)



GENERALIZED_ONSET_KMH = 40.0

GENERALIZED_FULL_IMPACT_KMH = 200.0

_GENERALIZED_BASE_COEFFS = (0.9366556, -0.0158458, 0.0001663888)


def _base_curve(u: float) -> float:
    c1, c2, c3 = _GENERALIZED_BASE_COEFFS
    return c1 * u + c2 * u**2 + c3 * u**3


def _solve_base_u_at(target_pct: float) -> float:
    """u where the base curve reaches `target_pct`, by bisection.

    Safe because the base curve is strictly increasing: the bracket always
    contains exactly one root.
    """
    lo, hi = 0.0, 1000.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if _base_curve(mid) < target_pct:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


_GENERALIZED_STRETCH = (GENERALIZED_FULL_IMPACT_KMH - GENERALIZED_ONSET_KMH) / _solve_base_u_at(100.0)

GENERALIZED_CURVE_COEFFS = (
    _GENERALIZED_BASE_COEFFS[0] / _GENERALIZED_STRETCH,
    _GENERALIZED_BASE_COEFFS[1] / _GENERALIZED_STRETCH**2,
    _GENERALIZED_BASE_COEFFS[2] / _GENERALIZED_STRETCH**3,
)


def generalized_affected_percentage(wind_kmh: float | None) -> float:
    """Percent of an area's own population affected at this wind speed."""
    v = _safe_float(wind_kmh)
    if v is None or v <= GENERALIZED_ONSET_KMH:
        return 0.0
    u = v - GENERALIZED_ONSET_KMH
    c1, c2, c3 = GENERALIZED_CURVE_COEFFS
    return max(0.0, c1 * u + c2 * u**2 + c3 * u**3)


_DISTRICT_ALIASES = {
    "jashore": "jessore",
    "barishal": "barisal",
    "chattogram": "chittagong",
    "coxbazar": "coxsbazar",
    "coxsbazaar": "coxsbazar",
}


def _norm_district_key(name: object) -> str:
    key = re.sub(r"[^a-z0-9]", "", str(name or "").lower())
    return _DISTRICT_ALIASES.get(key, key)


def _norm_place_key(name: object) -> str:
    """Normalise a union/upazila name for joining across datasets."""
    text = str(name or "").lower()
    text = re.sub(r"\b(union|paurashava|pourashava|city\s*corporation|upazila)\b", " ", text)
    return re.sub(r"[^a-z0-9]", "", text)


def _norm_impact_name(name: object) -> str:
    """Normalise an impact-model place while retaining administrative type."""
    text = str(name or "").lower()
    text = re.sub(r"\bpourasabha\b|\bpourashava\b", "paurashava", text)
    text = re.sub(r"\bunion\b", " ", text)
    return re.sub(r"[^a-z0-9]", "", text)


def _municipality_base(name: object, upazila: object = "") -> str:
    """Return the municipality's name without the Paurashava qualifier."""
    text = str(name or "").lower()
    text = re.sub(r"\b(paurashava|pourashava|pourasabha)\b", " ", text)
    base = re.sub(r"[^a-z0-9]", "", text)
    return base or _norm_place_key(upazila)


_IMPACT_LOOKUP_CACHE: dict | None = None


def load_impact_lookup(data_path: Path) -> dict:
    """Load the authoritative union allocation inputs from StructureDamageData."""
    global _IMPACT_LOOKUP_CACHE
    if _IMPACT_LOOKUP_CACHE is not None:
        return _IMPACT_LOOKUP_CACHE

    empty = {"records_by_district": {}, "dis_pop": {}, "district_households": {}}
    excel_path = Path(data_path) / "StructureDamageData.xlsx"
    if not excel_path.exists():
        print(f"[impact] {excel_path.name} not found — affected-population model disabled", flush=True)
        _IMPACT_LOOKUP_CACHE = empty
        return empty

    try:
        df = pd.read_excel(excel_path, sheet_name="Coastal_Housing_info")
    except Exception as exc:  # noqa: BLE001 - fail soft
        print(f"[impact] Failed to read {excel_path.name}: {exc}", flush=True)
        _IMPACT_LOOKUP_CACHE = empty
        return empty

    df["_d"] = df["District"].map(_norm_district_key)
    df["_u"] = df["Union"].map(_norm_impact_name)
    df["_up"] = df["Upazila"].map(_norm_place_key)
    records_by_district: dict[str, list[dict]] = {}
    for source_id, row in df.iterrows():
        district_key = _safe_str(row.get("_d"))
        if not district_key:
            continue
        union_label = _safe_str(row.get("Union"))
        is_municipality = bool(re.search(r"paurashava|pourashava|pourasabha", union_label, re.I))
        records_by_district.setdefault(district_key, []).append({
            "source_id": int(source_id),
            "upazila_key": _safe_str(row.get("_up")),
            "area_key": _safe_str(row.get("_u")),
            "municipality_base": _municipality_base(union_label, row.get("Upazila")),
            "is_municipality": is_municipality,
            "m": _safe_float(row.get("m")) or 0.0,
            "households": _safe_float(row.get("Households_No")) or 0.0,
        })

    workbook_dis_pop = df.dropna(subset=["Dis_Population"]).groupby("_d")["Dis_Population"].first().to_dict()
    district_shape_path = Path(data_path) / DISTRICT_2022_SHP
    direct_dis_pop: dict[str, float] = {}
    if district_shape_path.exists():
        district_boundaries = _read_bbs2022_boundary(district_shape_path, "district")
        direct_dis_pop = {
            _norm_district_key(row["DISTRICT_NAME"]): float(row["TOTAL_POP"])
            for _, row in district_boundaries.iterrows()
            if _safe_float(row.get("TOTAL_POP")) is not None
        }
    workbook_dis_pop.update(direct_dis_pop)

    lookup = {
        "records_by_district": records_by_district,
        "dis_pop": workbook_dis_pop,
        "district_households": df.groupby("_d")["Households_No"].sum().to_dict(),
    }
    print(
        f"[impact] Loaded affected-population lookup: {sum(len(v) for v in records_by_district.values())} areas, "
        f"{len(direct_dis_pop)} BBS 2022 district populations",
        flush=True,
    )
    _IMPACT_LOOKUP_CACHE = lookup
    return lookup


class AreaWinds(NamedTuple):
    """Representative wind speed for every area, built strictly bottom-up.

    union    -> the union's own wind, keyed by GEO_CODE
    upazila  -> mean of that upazila's union winds, keyed by (district, upazila)
    district -> mean of that district's *upazila* winds, keyed by district

    The district figure deliberately averages upazilas rather than unions, so
    an upazila with many small unions does not outweigh one with few. Every
    reported wind and every wind fed into the affected-population curve reads
    from here, so the number shown for an area is the number used for it.
    """

    union: dict
    upazila: dict
    district: dict


def compute_area_winds(table_classification: pd.DataFrame) -> AreaWinds:
    """Build the union → upazila → district wind hierarchy for this cyclone."""
    empty = AreaWinds({}, {}, {})
    if table_classification.empty or "District" not in table_classification.columns:
        return empty

    wind_col = (
        "Wind Speed (km/h)"
        if "Wind Speed (km/h)" in table_classification.columns
        else "Peak Wind Speed (km/h)"
    )
    if wind_col not in table_classification.columns:
        return empty

    tmp = table_classification.copy()
    tmp["_w"] = pd.to_numeric(tmp[wind_col], errors="coerce")
    tmp = tmp.dropna(subset=["_w"])
    if tmp.empty:
        return empty

    tmp["_d"] = tmp["District"].map(_norm_district_key)
    tmp["_u"] = tmp["Upazila"].map(_norm_place_key) if "Upazila" in tmp.columns else ""

    union_winds = {
        _safe_str(row.get("GEO_CODE")): float(row["_w"])
        for _, row in tmp.iterrows()
        if _safe_str(row.get("GEO_CODE"))
    }

    upazila_series = tmp.groupby(["_d", "_u"])["_w"].mean()
    upazila_winds = {key: float(value) for key, value in upazila_series.items()}

    district_winds = {
        key: float(value)
        for key, value in upazila_series.groupby(level=0).mean().items()
    }
    return AreaWinds(union_winds, upazila_winds, district_winds)


def compute_district_avg_wind(table_classification: pd.DataFrame) -> dict:
    """District wind: the mean of its upazila winds. See `compute_area_winds`."""
    return compute_area_winds(table_classification).district


def _current_population_and_structures(row: pd.Series) -> tuple[float, float | None]:
    """Return BBS 2022 population and a consistent structure-count denominator."""
    population = _safe_float(row.get("BBS Population"))
    direct_households = _safe_float(row.get("BBS Households"))
    household_size = _safe_float(row.get("BBS Household Size"))
    housing_counts = [
        _safe_float(row.get(column))
        for column in ("Kancha_num", "Semi-pucca_num", "Pucca_num")
    ]
    fallback_houses = sum(value for value in housing_counts if value is not None)
    if population is None or population <= 0:
        population = fallback_houses * 4.06 if fallback_houses > 0 else 0.0
    structures = direct_households
    if structures is None or structures <= 0:
        structures = (
            population / household_size
            if population > 0 and household_size is not None and household_size > 0
            else (fallback_houses if fallback_houses > 0 else None)
        )
    return float(population), _safe_float(structures)


def _proportional_shares(items: list[dict]) -> dict[str, float]:
    total = sum(max(0.0, float(item.get("population") or 0.0)) for item in items)
    if total > 0:
        return {
            item["geo_code"]: max(0.0, float(item.get("population") or 0.0)) / total
            for item in items
        }
    equal = 1.0 / len(items) if items else 0.0
    return {item["geo_code"]: equal for item in items}


def _apportion_integer(total: float, items: list[dict]) -> dict[str, int]:
    """Largest-remainder apportionment whose child integers sum to ``total``."""
    target = max(0, int(round(total)))
    shares = _proportional_shares(items)
    raw = {item["geo_code"]: target * shares[item["geo_code"]] for item in items}
    apportioned = {geo_code: int(math.floor(value)) for geo_code, value in raw.items()}
    remainder = target - sum(apportioned.values())
    order = sorted(raw, key=lambda geo_code: (raw[geo_code] - apportioned[geo_code], geo_code), reverse=True)
    for geo_code in order[:remainder]:
        apportioned[geo_code] += 1
    return apportioned


def build_impact_allocations(
    table_classification: pd.DataFrame,
    lookup: dict,
    partial_coverage: bool = False,
) -> dict[str, dict]:
    """Resolve union allocations while preserving workbook district totals.

    Exact workbook rows keep their stored ``m``. A workbook Paurashava row is
    split over its BBS 2022 ward polygons in proportion to ward population. Name
    changes are matched conservatively within the same upazila. Any remaining
    workbook weight is distributed across remaining BBS 2022 areas by population,
    so weights still sum to one and no source population is double counted.
    Districts absent from the workbook use BBS 2022 population shares directly.
    For partial tabular uploads, missing district areas are never redistributed
    onto the uploaded subset: exact workbook unions retain stored ``m`` and any
    unmatched uploaded area uses its own BBS 2022 population divided by the full
    district population.
    """
    allocations: dict[str, dict] = {}
    if table_classification.empty:
        return allocations

    table = table_classification.copy()
    table["_district_key"] = table["District"].map(_norm_district_key)
    for district_key, group in table.groupby("_district_key", sort=False):
        current: list[dict] = []
        for _, row in group.iterrows():
            geo_code = _safe_str(row.get("GEO_CODE"))
            if not geo_code:
                continue
            population, structures = _current_population_and_structures(row)
            union_label = _safe_str(row.get("Union"))
            municipality_label = _safe_str(row.get("Municipality"))
            is_municipality_area = bool(
                re.search(r"paurashava|pourashava|pourasabha", union_label, re.I)
            )
            current.append({
                "geo_code": geo_code,
                "upazila_key": _norm_place_key(row.get("Upazila")),
                "area_key": _norm_impact_name(row.get("Union")),
                "municipality_base": _municipality_base(
                    union_label if is_municipality_area else municipality_label,
                    row.get("Upazila"),
                ),
                "is_municipality_area": is_municipality_area,
                "is_municipal_ward": bool(municipality_label) and not is_municipality_area,
                "population": population,
                "structures": structures,
            })
        if not current:
            continue

        source_records = list((lookup.get("records_by_district") or {}).get(district_key, []))
        district_population = _safe_float((lookup.get("dis_pop") or {}).get(district_key))
        if not source_records or district_population is None or district_population <= 0:
            district_population = sum(item["population"] for item in current)
            shares = _proportional_shares(current)
            for item in current:
                allocations[item["geo_code"]] = {
                    "m": shares[item["geo_code"]],
                    "district_population": district_population,
                    "total_population": item["population"] or None,
                    "total_structures": item["structures"],
                    "allocation_method": "bbs2022_population_share",
                    "formula_source": "national_average_fallback",
                }
            continue

        source_by_id = {int(record["source_id"]): record for record in source_records}
        source_upazilas = sorted({_safe_str(record.get("upazila_key")) for record in source_records})

        def source_upazila(current_key: str) -> str:
            if current_key in source_upazilas:
                return current_key
            scored = sorted(
                ((SequenceMatcher(None, current_key, candidate).ratio(), candidate) for candidate in source_upazilas),
                reverse=True,
            )
            return scored[0][1] if scored and scored[0][0] >= 0.72 else current_key

        assigned_source: dict[int, list[dict]] = {}
        assigned_current: set[str] = set()

        for item in current:
            up_key = source_upazila(item["upazila_key"])
            candidates = [
                record for record in source_records
                if not record.get("is_municipality")
                and record.get("upazila_key") == up_key
                and record.get("area_key") == item["area_key"]
            ]
            if len(candidates) == 1:
                source_id = int(candidates[0]["source_id"])
                assigned_source.setdefault(source_id, []).append(item)
                assigned_current.add(item["geo_code"])

        if not partial_coverage or any(item["is_municipality_area"] for item in current):
            for item in current:
                eligible = item["is_municipal_ward"] if not partial_coverage else item["is_municipality_area"]
                if item["geo_code"] in assigned_current or not eligible:
                    continue
                up_key = source_upazila(item["upazila_key"])
                candidates = [
                    record for record in source_records
                    if record.get("is_municipality")
                    and record.get("upazila_key") == up_key
                    and record.get("municipality_base") == item["municipality_base"]
                ]
                if len(candidates) == 1:
                    source_id = int(candidates[0]["source_id"])
                    assigned_source.setdefault(source_id, []).append(item)
                    assigned_current.add(item["geo_code"])

        used_source_ids = set(assigned_source)
        for item in current:
            if item["geo_code"] in assigned_current or item["is_municipal_ward"]:
                continue
            up_key = source_upazila(item["upazila_key"])
            candidates = [
                record for record in source_records
                if int(record["source_id"]) not in used_source_ids
                and not record.get("is_municipality")
                and record.get("upazila_key") == up_key
            ]
            scored = sorted(
                (
                    (SequenceMatcher(None, item["area_key"], _safe_str(record.get("area_key"))).ratio(), record)
                    for record in candidates
                ),
                key=lambda pair: pair[0],
                reverse=True,
            )
            if scored and scored[0][0] >= 0.82 and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.05):
                source_id = int(scored[0][1]["source_id"])
                assigned_source[source_id] = [item]
                used_source_ids.add(source_id)
                assigned_current.add(item["geo_code"])

        for source_id, members in assigned_source.items():
            source = source_by_id[source_id]
            shares = _proportional_shares(members)
            fallback_structures = _apportion_integer(float(source["households"]), members)
            method = "workbook_m" if len(members) == 1 else "workbook_m_split_to_wards"
            for member in members:
                share = shares[member["geo_code"]]
                allocations[member["geo_code"]] = {
                    "m": float(source["m"]) * share,
                    "district_population": district_population,
                    "total_population": member["population"] or None,
                    "total_structures": member.get("structures") or fallback_structures[member["geo_code"]] or None,
                    "allocation_method": method,
                    "formula_source": "district_specific",
                }

        if partial_coverage:
            for member in current:
                if member["geo_code"] in assigned_current:
                    continue
                local_population = max(0.0, float(member.get("population") or 0.0))
                allocations[member["geo_code"]] = {
                    "m": local_population / district_population if district_population > 0 else 0.0,
                    "district_population": district_population,
                    "total_population": local_population or None,
                    "total_structures": member.get("structures"),
                    "allocation_method": "bbs2022_partial_district_population_share",
                    "formula_source": "district_specific",
                }
            continue

        assigned_m = sum(float(source_by_id[source_id]["m"]) for source_id in assigned_source)
        assigned_households = sum(float(source_by_id[source_id]["households"]) for source_id in assigned_source)
        residual_members = [item for item in current if item["geo_code"] not in assigned_current] or current
        residual_shares = _proportional_shares(residual_members)
        residual_m = max(0.0, 1.0 - assigned_m)
        district_households = _safe_float((lookup.get("district_households") or {}).get(district_key)) or 0.0
        residual_households = max(0.0, district_households - assigned_households)
        residual_structures = _apportion_integer(residual_households, residual_members)
        for member in residual_members:
            share = residual_shares[member["geo_code"]]
            existing = allocations.get(member["geo_code"])
            if existing:
                existing["m"] += residual_m * share
                if not (_safe_float(existing.get("total_structures")) or 0.0):
                    existing["total_structures"] = residual_structures[member["geo_code"]] or None
                existing["allocation_method"] += "+residual_population_share"
            else:
                allocations[member["geo_code"]] = {
                    "m": residual_m * share,
                    "district_population": district_population,
                    "total_population": member["population"] or None,
                    "total_structures": member.get("structures") or residual_structures[member["geo_code"]] or None,
                    "allocation_method": "workbook_residual_population_share",
                    "formula_source": "district_specific",
                }

    return allocations


def _clamp_percentage(value: float | None) -> float | None:
    """Bound a share-of-population figure to 0–100%.

    `people` comes from the district response curve (rate x m x district
    population) while the denominator is the area's own BBS 2022 population,
    so the two are not guaranteed consistent — an area whose workbook weight
    `m` outruns its BBS population share can produce a quotient above 100%.
    Nothing downstream benefits from reporting "134% of residents affected",
    and the risk classification is unchanged (anything over 80% is already
    Very High), so the reported share is capped.
    """
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return max(0.0, min(100.0, number))


def compute_affected_impact(
    wind_kmh: float | None,
    allocation: dict | None,
) -> dict:
    """Evaluate the affected-population curve for one area.

    `wind_kmh` is **that area's own** representative wind — the union's wind
    for a union, the upazila's (mean of its unions) for an upazila, the
    district's (mean of its upazilas) for a district. It is applied to that
    same area's own population, so the reported percentage *is* the curve
    value (bounded to 100%).

    The curve is applied unconditionally — the expected housing-damage class
    is not consulted here (see the model notes above).
    """
    allocation = allocation or {}
    x = _safe_float(wind_kmh)
    total_pop = _safe_float(allocation.get("total_population"))
    total_structures = _safe_float(allocation.get("total_structures"))
    if x is None or total_pop is None or total_pop <= 0:
        return {
            "impact_modelled": False,
            "affected_people": None,
            "affected_houses": None,
            "affected_people_pct": None,
            "affected_houses_pct": None,
            "model_wind_kmh": x,
            "total_population": int(round(total_pop)) if total_pop else None,
            "total_structures": int(round(total_structures)) if total_structures else None,
            "impact_formula_source": "unavailable",
            "impact_allocation_method": allocation.get("allocation_method", "unavailable"),
        }

    affected_rate = generalized_affected_percentage(x)
    people = int(round(affected_rate / 100.0 * total_pop))
    people = min(people, int(round(total_pop)))
    houses = int(round(people / 4.0))
    if total_structures is not None and total_structures > 0:
        houses = min(houses, int(round(total_structures)))
    people_pct = _clamp_percentage(people / total_pop * 100.0)
    houses_pct = _clamp_percentage(
        (houses / total_structures * 100.0) if total_structures and total_structures > 0 else None
    )
    return {
        "impact_modelled": True,
        "affected_people": people,
        "affected_houses": houses,
        "affected_people_pct": round(people_pct, 1) if people_pct is not None else None,
        "affected_houses_pct": round(houses_pct, 1) if houses_pct is not None else None,
        "model_wind_kmh": round(x, 1),
        "affected_rate_pct": round(affected_rate, 6),
        "total_population": int(round(total_pop)),
        "total_structures": int(round(total_structures)) if total_structures else None,
        "impact_formula_source": "generalized_curve",
        "impact_allocation_method": allocation.get("allocation_method", "bbs2022_area_population"),
    }


def _affected_population_breakdown(row: pd.Series, impact: dict) -> dict[str, int | None]:
    """Apportion an area's modelled affected total using BBS demographics.

    The hazard model produces one affected total for the area's own
    population. Each requested demographic count is therefore the same total
    multiplied by that demographic's BBS share of the area's population.
    ``None`` is preserved when either the impact or the required BBS field is
    unavailable, rather than presenting an invented zero.
    """
    affected = _safe_float(impact.get("affected_people"))
    total_population = _safe_float(impact.get("total_population"))
    result: dict[str, int | None] = {"total": int(round(affected)) if affected is not None else None}
    sources = {
        "male": "BBS Male Population",
        "female": "BBS Female Population",
        "age_0_4": "BBS Age 0-4",
        "age_5_19": "BBS Age 5-19",
        "age_60_plus": "BBS Age 60+",
    }
    for key, column in sources.items():
        demographic_total = _safe_float(row.get(column))
        if affected is None or total_population is None or total_population <= 0 or demographic_total is None:
            result[key] = None
            continue
        result[key] = int(round(affected * max(0.0, demographic_total) / total_population))
    return result


def attach_affected_population_risk(
    table_classification: pd.DataFrame,
    data_path: Path,
    partial_coverage: bool = False,
) -> pd.DataFrame:
    """Add affected-population outputs and their deterministic risk label.

    Risk has no independent score. It is derived only from
    ``Affected Population (%)`` using the thresholds requested by the model:
    <20 Very Low, 20–<40 Low, 40–<60 Medium, 60–80 High, and >80 Very High.

    The housing-damage table is not consulted: affected population comes from
    the district response curve alone.
    """
    table = table_classification.copy()
    impact_lookup = load_impact_lookup(data_path)
    area_winds = compute_area_winds(table)
    allocations = build_impact_allocations(
        table,
        impact_lookup,
        partial_coverage=partial_coverage,
    )

    impacts: list[dict] = []
    for _, row in table.iterrows():
        geo_code = _safe_str(row.get("GEO_CODE", ""))
        impacts.append(
            compute_affected_impact(
                wind_kmh=area_winds.union.get(geo_code),
                allocation=allocations.get(geo_code),
            )
        )

    table["Affected Population"] = [item.get("affected_people") for item in impacts]
    table["Total Population"] = [item.get("total_population") for item in impacts]
    table["Affected Population (%)"] = [item.get("affected_people_pct") for item in impacts]
    breakdowns = [
        _affected_population_breakdown(row, impact)
        for (_, row), impact in zip(table.iterrows(), impacts)
    ]
    table["Affected Male"] = [item.get("male") for item in breakdowns]
    table["Affected Female"] = [item.get("female") for item in breakdowns]
    table["Affected Age 0-4"] = [item.get("age_0_4") for item in breakdowns]
    table["Affected Age 5-19"] = [item.get("age_5_19") for item in breakdowns]
    table["Affected Age 60+"] = [item.get("age_60_plus") for item in breakdowns]
    exact_percentages = [
        _clamp_percentage(
            (float(item["affected_people"]) / float(item["total_population"]) * 100.0)
            if item.get("affected_people") is not None and item.get("total_population")
            else None
        )
        for item in impacts
    ]
    table["Risk"] = [affected_population_risk(value) for value in exact_percentages]
    return table


def _blank(value: object) -> bool:
    """True for the several ways 'no value' shows up across these tables."""
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(value, str) and not value.strip()


def build_union_adjacency(gdf: gpd.GeoDataFrame) -> dict[str, list[str]]:
    """GEO_CODE -> GEO_CODEs of the unions whose boundaries it shares.

    Built with the spatial index rather than an O(n²) sweep — there are ~8 200
    union polygons. `intersects` (not `touches`) is used deliberately: the BBS
    boundaries have slivers and near-misses along rivers where two polygons do
    not share an exact edge, and those are precisely the areas that need a
    neighbour to borrow from.
    """
    if gdf is None or gdf.empty or "GEO_CODE" not in gdf.columns:
        return {}
    frame = gdf[["GEO_CODE", "geometry"]].copy()
    frame["GEO_CODE"] = frame["GEO_CODE"].astype(str)
    frame = frame[frame.geometry.notna() & ~frame.geometry.is_empty].reset_index(drop=True)
    if frame.empty:
        return {}

    left, right = frame.sindex.query(frame.geometry, predicate="intersects")
    codes = frame["GEO_CODE"].tolist()
    adjacency: dict[str, list[str]] = {code: [] for code in codes}
    for i, j in zip(left, right):
        if i == j:
            continue
        adjacency[codes[i]].append(codes[j])
    return adjacency


def fill_gaps_from_neighbours(
    table: pd.DataFrame,
    gdf: gpd.GeoDataFrame,
    numeric_columns: Sequence[str] = (),
    categorical_columns: Sequence[str] = (),
    max_passes: int = 3,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Fill blank metric cells from the values of adjoining unions.

    A handful of unions carry no value of their own — most often because BBS
    2022 records no resident population there (river chars, reserved forest),
    so a population-denominated figure like Risk is undefined. On a choropleth
    those render as grey holes punched through an otherwise continuous
    surface. Each hole is closed using its immediate neighbours:

      * categorical columns (Risk) take the **mode** of the neighbouring
        classes — ties break toward the more severe class, so a gap between a
        High and a Medium union is never optimistically filled;
      * numeric columns take the neighbours' **median**. A mode is meaningless
        for continuous metres/km-per-hour readings where every value is
        distinct; the median is the robust equivalent of "what the surrounding
        area looks like".

    Runs a few passes so a hole whose neighbours are themselves holes still
    closes, and never overwrites a real value. Returns the filled table plus a
    per-column count of how many cells were estimated.
    """
    filled_counts: dict[str, int] = {}
    columns = [c for c in (*numeric_columns, *categorical_columns) if c in table.columns]
    if table.empty or not columns:
        return table, filled_counts

    adjacency = build_union_adjacency(gdf)
    if not adjacency:
        return table, filled_counts

    table = table.copy()
    geo = table["GEO_CODE"].astype(str)
    row_by_geo = {code: idx for idx, code in zip(table.index, geo)}
    severity_rank = {name: i for i, name in enumerate(_RISK_ORDER)}

    for column in columns:
        is_categorical = column in categorical_columns
        for _ in range(max_passes):
            missing = [code for code, idx in row_by_geo.items() if _blank(table.at[idx, column])]
            if not missing:
                break
            resolved: dict[str, object] = {}
            for code in missing:
                values = [
                    table.at[row_by_geo[n], column]
                    for n in adjacency.get(code, [])
                    if n in row_by_geo and not _blank(table.at[row_by_geo[n], column])
                ]
                if not values:
                    continue
                if is_categorical:
                    counts = Counter(str(v) for v in values)
                    top = max(counts.values())
                    tied = [v for v, c in counts.items() if c == top]
                    resolved[code] = max(tied, key=lambda v: severity_rank.get(v, -1))
                else:
                    numbers = [n for n in (_safe_float(v) for v in values) if n is not None]
                    if not numbers:
                        continue
                    resolved[code] = float(statistics.median(numbers))
            if not resolved:
                break
            for code, value in resolved.items():
                table.at[row_by_geo[code], column] = value
            filled_counts[column] = filled_counts.get(column, 0) + len(resolved)

    return table, filled_counts


def build_union_contexts(
    table_classification: pd.DataFrame,
    table_damage: pd.DataFrame,
    table_rainfall_evac: pd.DataFrame,
    data_path: Path | None = None,
    partial_coverage: bool = False,
) -> list[dict]:
    """Aggregate per-union analytics for downstream LLM prompting."""

    impact_lookup = load_impact_lookup(data_path or BASE_DATA_DIR)
    area_winds = compute_area_winds(table_classification)
    impact_allocations = build_impact_allocations(
        table_classification,
        impact_lookup,
        partial_coverage=partial_coverage,
    )

    damage_lookup: dict[str, dict] = {}
    if not table_damage.empty:
        damage_types = [
            col.replace(" Damage", "")
            for col in table_damage.columns
            if col.endswith(" Damage")
        ]
        for _, row in table_damage.iterrows():
            union_name = _safe_str(row.get("Union", ""))
            geo_code = _safe_str(row.get("GEO_CODE", "")) or union_name
            damage_lookup[geo_code] = {
                "risk": _safe_str(row.get("Risk", "")),
                "wind_speed": _safe_float(row.get("Wind Speed (km/h)")),
                "total_rainfall": _safe_float(row.get("Total Rainfall (mm)")),
                "damage": {
                    typ: _safe_str(row.get(f"{typ} Damage", ""))
                    for typ in damage_types
                },
                "evacuate": {
                    typ: _safe_str(row.get(f"{typ} Evacuate", "No")).lower() == "yes"
                    for typ in damage_types
                },
            }

    rainfall_lookup: dict[str, list[dict]] = {}
    if not table_rainfall_evac.empty:
        rainfall_key = "GEO_CODE" if "GEO_CODE" in table_rainfall_evac.columns else "Union"
        for area_key, group in table_rainfall_evac.groupby(rainfall_key):
            rainfall_lookup[_safe_str(area_key)] = [
                {
                    "house_types": _safe_str(row.get("Evacuate House Types", "")),
                    "rainfall_mm_per_day": _safe_float(row.get("Rainfall (mm/day)")),
                }
                for _, row in group.iterrows()
            ]

    contexts: list[dict] = []
    for _, row in table_classification.iterrows():
        union_name = _safe_str(row.get("Union", ""))
        geo_code = _safe_str(row.get("GEO_CODE", ""))
        housing_percentages = {
            "Kancha": _safe_percent(row.get("Kancha (%)")),
            "Semi-pucca": _safe_percent(row.get("Semi-pucca (%)")),
            "Pucca": _safe_percent(row.get("Pucca (%)")),
        }
        housing_numbers = {
            "Kancha": _safe_float(row.get("Kancha_num")),
            "Semi-pucca": _safe_float(row.get("Semi-pucca_num")),
            "Pucca": _safe_float(row.get("Pucca_num")),
        }
        wind_speed = _safe_float(row.get("Wind Speed (km/h)"))
        upazila_name = _safe_str(row.get("Upazila", ""))
        district_name = _safe_str(row.get("District", ""))
        context = {
            "admin_level": "union",
            "name": union_name,
            "geo_code": geo_code,
            "boundary_geo_code": _safe_str(row.get("Boundary GEO_CODE", "")),
            "union": union_name,
            "upazila": upazila_name,
            "upazila_name": upazila_name,
            "district": district_name,
            "wind_speed_kmh": wind_speed,
            "wind_class_label": get_imd_wind_category(wind_speed) if wind_speed is not None else "",
            "total_rainfall_mm": _safe_float(row.get("Total Rainfall (mm)")),
            "storm_surge_m": _safe_float(row.get("Storm Surge (m)")),
            "risk": _safe_str(row.get("Risk", "")),
            "housing_percentages": housing_percentages,
            "housing_numbers": housing_numbers,
        }
        damage = damage_lookup.get(geo_code, damage_lookup.get(union_name, {}))
        context["expected_damage"] = damage.get("damage", {})
        full_damage_types = [
            typ
            for typ, status in context["expected_damage"].items()
            if _damage_severity(status) >= 3
        ]
        context["full_damage_house_types"] = full_damage_types
        context["evacuation_flags"] = {
            typ: typ in full_damage_types for typ in HOUSE_TYPES_NUM
        }
        context["wind_speed_from_damage"] = damage.get("wind_speed")
        context["total_rainfall_from_damage"] = damage.get("total_rainfall")
        context["rainfall_evacuation"] = rainfall_lookup.get(
            geo_code, rainfall_lookup.get(union_name, [])
        )

        impact = compute_affected_impact(
            wind_kmh=area_winds.union.get(geo_code),
            allocation=impact_allocations.get(geo_code),
        )
        context.update(impact)
        context["affected_population_breakdown"] = _affected_population_breakdown(row, impact)
        context["risk"] = _safe_str(row.get("Risk", ""))
        contexts.append(context)

    return contexts


def _damage_severity(value: object) -> int:
    text = _safe_str(value).lower()
    if "full" in text or "complete" in text:
        return 3
    if "partial" in text or "major" in text:
        return 2
    if "minor" in text:
        return 1
    return 0


def build_aggregate_contexts(
    union_contexts: list[dict],
    admin_level: str,
) -> list[dict]:
    """Aggregate deterministic union analytics to upazila or district level.

    Weather values use the maximum (or mean, for wind) across member unions,
    housing counts are summed, housing shares are recomputed from those
    counts, and damage/risk fields retain the most severe member-union
    outcome. This keeps higher-level guidance conservative without inventing
    values that are absent upstream.

    Affected population/houses are a straight **sum of the member contexts'**
    own affected_people/affected_houses — computed once at union level and
    rolled up, never re-evaluated from a mean wind at this level. Calling this
    with `admin_level="district"` on already-built upazila contexts therefore
    sums upazilas, each of which already sums its unions.
    """
    if admin_level not in {"upazila", "district"}:
        raise ValueError("admin_level must be 'upazila' or 'district'")

    groups: dict[tuple[str, ...], list[dict]] = {}
    for ctx in union_contexts:
        district = _safe_str(ctx.get("district"))
        upazila = _safe_str(ctx.get("upazila"))
        if admin_level == "upazila":
            if not upazila:
                continue
            key = (district, upazila)
        else:
            if not district:
                continue
            key = (district,)
        groups.setdefault(key, []).append(ctx)

    aggregated: list[dict] = []
    for key, members in groups.items():
        district = key[0]
        upazila = key[1] if admin_level == "upazila" else ""
        name = upazila if admin_level == "upazila" else district

        housing_numbers: dict[str, float] = {}
        for typ in HOUSE_TYPES_NUM:
            housing_numbers[typ] = float(
                sum(
                    value
                    for member in members
                    if (value := _safe_float((member.get("housing_numbers") or {}).get(typ))) is not None
                )
            )
        total_houses = sum(housing_numbers.values())
        housing_percentages = {
            typ: round((count / total_houses) * 100.0, 2) if total_houses > 0 else None
            for typ, count in housing_numbers.items()
        }

        expected_damage: dict[str, str] = {}
        for typ in HOUSE_TYPES_NUM:
            candidates = [
                _safe_str((member.get("expected_damage") or {}).get(typ))
                for member in members
            ]
            expected_damage[typ] = max(candidates, key=_damage_severity, default="")

        full_damage_types = [
            typ for typ, damage in expected_damage.items() if _damage_severity(damage) >= 3
        ]
        rainfall_actions: dict[str, float | None] = {}
        for member in members:
            for action in member.get("rainfall_evacuation") or []:
                house_types = _safe_str(action.get("house_types"))
                if not house_types:
                    continue
                rainfall = _safe_float(action.get("rainfall_mm_per_day"))
                previous = rainfall_actions.get(house_types)
                if previous is None or (rainfall is not None and rainfall > previous):
                    rainfall_actions[house_types] = rainfall

        def max_numeric(field: str) -> float | None:
            values = [
                value
                for member in members
                if (value := _safe_float(member.get(field))) is not None
            ]
            return max(values) if values else None

        def mean_numeric(field: str) -> float | None:
            """Average a field across member areas.

            Wind speed is area-representative rather than worst-case, so
            upazila/district wind is the mean of its member unions — matching
            the spatial averaging already applied inside each union.
            """
            values = [
                value
                for member in members
                if (value := _safe_float(member.get(field))) is not None
            ]
            return sum(values) / len(values) if values else None

        wind_speed = mean_numeric("wind_speed_kmh")
        context = {
            "admin_level": admin_level,
            "name": name,
            "geo_code": f"{admin_level}:{'|'.join(key)}",
            "union": "",
            "upazila": upazila,
            "upazila_name": upazila,
            "district": district,
            "member_count": (
                int(sum(int(member.get("member_count") or 1) for member in members))
                if admin_level == "district"
                else len(members)
            ),
            "wind_speed_kmh": wind_speed,
            "wind_class_label": get_imd_wind_category(wind_speed) if wind_speed is not None else "",
            "total_rainfall_mm": max_numeric("total_rainfall_mm"),
            "storm_surge_m": max_numeric("storm_surge_m"),
            "risk": "",
            "housing_percentages": housing_percentages,
            "housing_numbers": housing_numbers,
            "expected_damage": expected_damage,
            "evacuation_flags": {typ: typ in full_damage_types for typ in HOUSE_TYPES_NUM},
            "full_damage_house_types": full_damage_types,
            "rainfall_evacuation": [
                {"house_types": typ, "rainfall_mm_per_day": rainfall}
                for typ, rainfall in sorted(rainfall_actions.items())
            ],
        }

        modelled = [m_ctx for m_ctx in members if m_ctx.get("impact_modelled")]
        if modelled:
            def _sum(field: str) -> float:
                return float(
                    sum(
                        value
                        for member in modelled
                        if (value := _safe_float(member.get(field))) is not None
                    )
                )

            people = _sum("affected_people")
            houses = _sum("affected_houses")
            pop_total = _sum("total_population")
            struct_total = _sum("total_structures")

            breakdown: dict[str, int | None] = {"total": int(round(people))}
            for key in DEMOGRAPHIC_AFFECTED_KEYS:
                values = [
                    _safe_float((member.get("affected_population_breakdown") or {}).get(key))
                    for member in modelled
                ]
                breakdown[key] = (
                    int(round(sum(value for value in values if value is not None)))
                    if all(value is not None for value in values)
                    else None
                )

            people_pct = _clamp_percentage(people / pop_total * 100.0) if pop_total else None
            houses_pct = _clamp_percentage(houses / struct_total * 100.0) if struct_total else None
            context.update({
                "impact_modelled": True,
                "affected_people": int(round(people)),
                "affected_houses": int(round(houses)),
                "affected_people_pct": round(people_pct, 1) if people_pct is not None else None,
                "affected_houses_pct": round(houses_pct, 1) if houses_pct is not None else None,
                "model_wind_kmh": None,
                "total_population": int(round(pop_total)) if pop_total else None,
                "total_structures": int(round(struct_total)) if struct_total else None,
                "impact_formula_source": "sum_of_members",
                "impact_allocation_method": (
                    f"sum_of_member_{'unions' if admin_level == 'upazila' else 'upazilas'}"
                ),
                "affected_population_breakdown": breakdown,
            })
            context["risk"] = affected_population_risk(people_pct)
        else:
            context.update({
                "impact_modelled": False,
                "affected_people": None,
                "affected_houses": None,
                "affected_people_pct": None,
                "affected_houses_pct": None,
                "model_wind_kmh": None,
                "total_population": None,
                "total_structures": int(round(total_houses)) if total_houses else None,
                "impact_formula_source": "unavailable",
                "impact_allocation_method": "unavailable",
                "affected_population_breakdown": {key: None for key in ("total", *DEMOGRAPHIC_AFFECTED_KEYS)},
            })
            context["risk"] = ""
        aggregated.append(context)

    return sorted(
        aggregated,
        key=lambda ctx: (
            _safe_str(ctx.get("district")).lower(),
            _safe_str(ctx.get("name")).lower(),
        ),
    )


def build_full_upazila_contexts(
    union_contexts: list[dict],
    upazila_weather: pd.DataFrame,
) -> list[dict]:
    """Merge full-coverage upazila weather with union-derived impact data.

    Weather, population, households, and C14 housing percentages cover every
    boundary row. Only legacy house-type counts may remain empty when
    union_bbs.csv has no matching code; that never removes an area.
    """
    housing_contexts = build_aggregate_contexts(union_contexts, "upazila")
    lookup = {
        (_normalize_district(ctx.get("district", "")), _normalize_name(ctx.get("name", ""))): ctx
        for ctx in housing_contexts
    }

    weather = upazila_weather.copy()
    for column in ("UPAZILA_NAME", "DISTRICT_NAME"):
        if column not in weather.columns:
            weather[column] = ""
        weather[column] = weather[column].fillna("").astype(str).str.strip()

    contexts: list[dict] = []
    for (district, upazila), group in weather.groupby(
        ["DISTRICT_NAME", "UPAZILA_NAME"], dropna=False, sort=True
    ):
        district = _safe_str(district)
        upazila = _safe_str(upazila)
        if not upazila:
            continue
        key = (_normalize_district(district), _normalize_name(upazila))
        base = dict(lookup.get(key, {}))

        def group_max(column: str) -> float | None:
            if column not in group.columns:
                return None
            values = pd.to_numeric(group[column], errors="coerce").dropna()
            return float(values.max()) if not values.empty else None

        def group_mean(column: str) -> float | None:
            """Area-average across the grid rows backing this upazila."""
            if column not in group.columns:
                return None
            values = pd.to_numeric(group[column], errors="coerce").dropna()
            return float(values.mean()) if not values.empty else None

        geo_codes = [_safe_str(value) for value in group.get("GEO_CODE", pd.Series(dtype=str))]
        base.update(
            {
                "admin_level": "upazila",
                "name": upazila,
                "geo_code": geo_codes[0] if len(geo_codes) == 1 else f"upazila:{district}|{upazila}",
                "union": "",
                "upazila": upazila,
                "upazila_name": upazila,
                "district": district,
                "wind_speed_kmh": group_mean("mean_ws_kmh"),
                "total_rainfall_mm": group_max("max_total_rainfall"),
                "storm_surge_m": group_max("max_storm_surge_m"),
            }
        )
        direct_percentages = {
            "Kancha": group_max("KANCHA_PCT"),
            "Semi-pucca": group_max("SEMI_PUCCA_PCT"),
            "Pucca": group_max("PUCCA_PCT"),
        }
        if any(value is not None for value in direct_percentages.values()):
            base["housing_percentages"] = direct_percentages

        direct_demographics = {
            "BBS Male Population": group_max("MALE_POP"),
            "BBS Female Population": group_max("FEMALE_POP"),
            "BBS Age 0-4": group_max("AGE_0_4"),
            "BBS Age 5-19": group_max("AGE_5_19"),
            "BBS Age 60+": group_max("AGE_60_PLUS"),
        }
        direct_total_population = group_max("TOTAL_POP")
        if direct_total_population is not None:
            base["affected_population_breakdown"] = _affected_population_breakdown(
                pd.Series(direct_demographics),
                {
                    "affected_people": base.get("affected_people"),
                    "total_population": direct_total_population,
                },
            )

        wind_speed = _safe_float(base.get("wind_speed_kmh"))
        base["wind_class_label"] = get_imd_wind_category(wind_speed) if wind_speed is not None else ""
        base.setdefault("member_count", 0)
        base.setdefault("housing_percentages", {})
        base.setdefault("housing_numbers", {})
        base.setdefault("expected_damage", {})
        base.setdefault("full_damage_house_types", [])
        base.setdefault("evacuation_flags", {})
        base.setdefault("rainfall_evacuation", [])
        base.setdefault("impact_modelled", False)
        for field in (
            "affected_people",
            "affected_houses",
            "affected_people_pct",
            "affected_houses_pct",
            "model_wind_kmh",
            "total_population",
            "total_structures",
        ):
            base.setdefault(field, None)
        base.setdefault(
            "affected_population_breakdown",
            {key: None for key in ("total", *DEMOGRAPHIC_AFFECTED_KEYS)},
        )
        contexts.append(base)

    return sorted(
        contexts,
        key=lambda ctx: (
            _safe_str(ctx.get("district")).lower(),
            _safe_str(ctx.get("name")).lower(),
        ),
    )


def enrich_district_contexts_from_boundaries(
    contexts: list[dict],
    gdf_district: gpd.GeoDataFrame,
) -> list[dict]:
    """Use the 2022 district polygon's population and C14 percentages."""
    if gdf_district is None or gdf_district.empty:
        return contexts
    lookup = {
        _norm_district_key(row.get("DISTRICT_NAME")): row
        for _, row in gdf_district.iterrows()
    }
    enriched: list[dict] = []
    for source in contexts:
        context = dict(source)
        row = lookup.get(_norm_district_key(context.get("district")))
        if row is None:
            enriched.append(context)
            continue
        context["housing_percentages"] = {
            "Kancha": _safe_float(row.get("KANCHA_PCT")),
            "Semi-pucca": _safe_float(row.get("SEMI_PUCCA_PCT")),
            "Pucca": _safe_float(row.get("PUCCA_PCT")),
        }
        direct_total_population = _safe_float(row.get("TOTAL_POP"))
        if direct_total_population is not None:
            context["affected_population_breakdown"] = _affected_population_breakdown(
                pd.Series(
                    {
                        "BBS Male Population": row.get("MALE_POP"),
                        "BBS Female Population": row.get("FEMALE_POP"),
                        "BBS Age 0-4": row.get("AGE_0_4"),
                        "BBS Age 5-19": row.get("AGE_5_19"),
                        "BBS Age 60+": row.get("AGE_60_PLUS"),
                    }
                ),
                {
                    "affected_people": context.get("affected_people"),
                    "total_population": direct_total_population,
                },
            )
        enriched.append(context)
    return enriched


def fill_missing_with_nearest_union(gdf_all: gpd.GeoDataFrame, value_col: str) -> gpd.GeoDataFrame:
    """
    Fill missing values in a GeoDataFrame column with the value from the
    nearest non-null union (based on centroid distance).

    Parameters
    ----------
    gdf_all : geopandas.GeoDataFrame
        GeoDataFrame containing geometry and a column with potential nulls.
    value_col : str
        Name of the column whose missing values should be filled.

    Returns
    -------
    geopandas.GeoDataFrame
        A copy of the input GeoDataFrame with missing values in `value_col`
        replaced by values from the nearest valid neighbour.
    """
    null_mask = gdf_all[value_col].isnull()
    valid = gdf_all[~null_mask].copy()
    nulls = gdf_all[null_mask].copy()

    if nulls.empty:
        return gdf_all
    
    if valid.empty:
        return gdf_all

    projected_crs = "EPSG:32646"  # UTM 46N covers Bangladesh
    valid_proj = valid.to_crs(projected_crs)
    nulls_proj = nulls.to_crs(projected_crs)

    valid_centroids = np.array([[g.centroid.x, g.centroid.y] for g in valid_proj.geometry])
    valid_values = valid[value_col].values

    for orig_idx, proj_row in nulls_proj.iterrows():
        null_centroid = np.array([proj_row.geometry.centroid.x, proj_row.geometry.centroid.y])
        distances = np.sqrt(np.sum((valid_centroids - null_centroid) ** 2, axis=1))
        nearest_idx = np.argmin(distances)
        gdf_all.at[orig_idx, value_col] = valid_values[nearest_idx]
    
    return gdf_all

def _resolve_data_dir(data_dir: str | Path | None) -> Path:
    if data_dir is None:
        return BASE_DATA_DIR
    candidate = Path(data_dir).expanduser().resolve()
    if not candidate.exists():
        raise FileNotFoundError(f"Data directory not found: {candidate}")
    return candidate



_COMPASS_16 = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]

_COMPASS_BN = {
    "N": "উত্তর", "NNE": "উত্তর-উত্তরপূর্ব", "NE": "উত্তরপূর্ব", "ENE": "পূর্ব-উত্তরপূর্ব",
    "E": "পূর্ব", "ESE": "পূর্ব-দক্ষিণপূর্ব", "SE": "দক্ষিণপূর্ব", "SSE": "দক্ষিণ-দক্ষিণপূর্ব",
    "S": "দক্ষিণ", "SSW": "দক্ষিণ-দক্ষিণপশ্চিম", "SW": "দক্ষিণপশ্চিম", "WSW": "পশ্চিম-দক্ষিণপশ্চিম",
    "W": "পশ্চিম", "WNW": "পশ্চিম-উত্তরপশ্চিম", "NW": "উত্তরপশ্চিম", "NNW": "উত্তর-উত্তরপশ্চিম",
}

_COMPASS_EN = {
    "N": "North", "NNE": "North-Northeast", "NE": "Northeast", "ENE": "East-Northeast",
    "E": "East", "ESE": "East-Southeast", "SE": "Southeast", "SSE": "South-Southeast",
    "S": "South", "SSW": "South-Southwest", "SW": "Southwest", "WSW": "West-Southwest",
    "W": "West", "WNW": "West-Northwest", "NW": "Northwest", "NNW": "North-Northwest",
}


def _compass_bearing(dlat: float, dlon: float) -> tuple[str, float]:
    """Compass point + degrees for a movement of (dlat, dlon)."""
    if abs(dlat) < 1e-9 and abs(dlon) < 1e-9:
        return "", 0.0
    ang = math.degrees(math.atan2(dlon, dlat)) % 360.0
    return _COMPASS_16[int((ang + 11.25) // 22.5) % 16], round(ang, 1)


def _imd_category_en(ws: float | None) -> str:
    """IMD category label without the km/h suffix (system-level classification)."""
    full = get_imd_wind_category(ws if ws is not None else -1)
    return full.split(" (")[0] if "(" in full else full


def analyze_cyclone_track(
    nc_input: bytes | str | Path,
    gdf_union_full: gpd.GeoDataFrame,
    cyclone_name: str | None = None,
) -> dict:
    """Return current + forecast (landfall) state derived from the wind file.

    Fails soft: any problem returns ``{"available": False}`` so guideline
    generation still proceeds with whatever the user typed.
    """
    temp_path: str | None = None
    if isinstance(nc_input, (str, Path)):
        nc_path = str(nc_input)
    else:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".nc") as tmp:
            tmp.write(nc_input)
            nc_path = tmp.name
        temp_path = nc_path

    try:
        with _NETCDF_READ_LOCK, Dataset(nc_path) as nc:
            lats = np.asarray(nc["lat"][:], dtype=float)
            lons = np.asarray(nc["lon"][:], dtype=float)
            u10 = nc["u10"][:]
            v10 = nc["v10"][:]
            tvar = nc["time"]
            tvals = np.asarray(tvar[:], dtype=float)
            t_units = getattr(tvar, "units", "hours since 1970-01-01 00:00:00")
            t_calendar = getattr(tvar, "calendar", "standard")

        nt = int(u10.shape[0])
        if nt == 0:
            return {"available": False}

        dates = None
        try:
            dates = num2date(tvals, t_units, t_calendar)
            iso_dates = [d.isoformat() if d is not None else None for d in dates]
        except Exception:
            iso_dates = [None] * nt

        centers: list[tuple[float, float, float]] = []
        for t in range(nt):
            u = np.squeeze(np.ma.filled(u10[t], np.nan)).astype(float)
            v = np.squeeze(np.ma.filled(v10[t], np.nan)).astype(float)
            spd = np.hypot(u, v) * 3.6  # km/h
            if not np.isfinite(spd).any():
                centers.append((float("nan"), float("nan"), 0.0))
                continue
            threshold = float(np.nanpercentile(spd, 99.5))
            mask = np.isfinite(spd) & (spd >= threshold)
            weights = np.where(mask, np.square(spd), 0.0)
            weight_sum = float(np.nansum(weights))
            if weight_sum <= 0:
                fi = np.unravel_index(np.nanargmax(spd), spd.shape)
                center_lat = float(lats[fi[0]])
                center_lon = float(lons[fi[1]])
            else:
                center_lat = float(np.nansum(weights * lats[:, None]) / weight_sum)
                center_lon = float(np.nansum(weights * lons[None, :]) / weight_sum)
            centers.append((center_lat, center_lon, float(np.nanmax(spd))))

        cur_lat, cur_lon, cur_wind = centers[0]

        landfall_idx: int | None = None
        landfall_district = ""
        landfall_upazila = ""
        landfall_union = ""
        landfall_detection_method = "first_model_track_point_within_union"
        try:
            pts = gpd.GeoDataFrame(
                {"t": list(range(nt))},
                geometry=gpd.points_from_xy(
                    [c[1] for c in centers], [c[0] for c in centers]
                ),
                crs="EPSG:4326",
            )
            cols = [
                c
                for c in (
                    "GEO_CODE",
                    "UNION_NAME",
                    "UPAZILA_NAME",
                    "DISTRICT_NAME",
                    "geometry",
                )
                if c in gdf_union_full.columns
            ]
            joined = gpd.sjoin(pts, gdf_union_full[cols], how="left", predicate="within")
            joined = joined.sort_values("t")
            on_land = joined.dropna(subset=[c for c in ("DISTRICT_NAME", "UNION_NAME") if c in joined.columns][:1] or ["index_right"])
            if not on_land.empty:
                first = on_land.iloc[0]
                landfall_idx = int(first["t"])
                landfall_district = _safe_str(first.get("DISTRICT_NAME", "")) if "DISTRICT_NAME" in joined.columns else ""
                landfall_upazila = _safe_str(first.get("UPAZILA_NAME", "")) if "UPAZILA_NAME" in joined.columns else ""
                landfall_union = _safe_str(first.get("UNION_NAME", "")) if "UNION_NAME" in joined.columns else ""
        except Exception as exc:  # noqa: BLE001
            print(f"[track] landfall point-in-polygon failed: {exc}", flush=True)

        if landfall_idx is None:
            band = [
                t for t in range(nt)
                if np.isfinite(centers[t][0]) and centers[t][0] >= 21.0 and 88.0 <= centers[t][1] <= 93.0
            ]
            if band:
                landfall_idx = max(band, key=lambda t: centers[t][2])
            else:
                landfall_idx = int(np.nanargmax([c[2] for c in centers]))
            landfall_detection_method = "fallback_peak_in_coastal_band"

        lf_lat, lf_lon, lf_wind = centers[landfall_idx]

        comp, ang = _compass_bearing(lf_lat - cur_lat, lf_lon - cur_lon)
        direction_bn = ""
        direction_en = ""
        if comp:
            direction_bn = f"{_COMPASS_BN.get(comp, comp)} ({comp})"
            direction_en = f"{_COMPASS_EN.get(comp, comp)} ({comp})"

        lead_hours = 0.0
        if dates is not None and landfall_idx < len(dates):
            try:
                lead_hours = float((dates[landfall_idx] - dates[0]).total_seconds() / 3600.0)
            except Exception:
                lead_hours = 0.0
        if lead_hours == 0.0 and landfall_idx < len(tvals):
            lead_hours = float(tvals[landfall_idx] - tvals[0])

        current_over_sea = True
        try:
            if landfall_idx == 0:
                current_over_sea = False
        except Exception:
            pass
        coords = f"~{cur_lat:.1f}°N, {cur_lon:.1f}°E"
        current_location_label = f"বঙ্গোপসাগর ({coords})" if current_over_sea else coords
        current_location_label_en = f"Bay of Bengal ({coords})" if current_over_sea else coords

        landfall_place = ", ".join(
            [p for p in (landfall_union, landfall_upazila, landfall_district) if p]
        ) or f"উপকূলীয় স্থান (~{lf_lat:.2f}°N, {lf_lon:.2f}°E)"
        landfall_place_en = ", ".join(
            [p for p in (landfall_union, landfall_upazila, landfall_district) if p]
        ) or f"Coastal location (~{lf_lat:.2f}°N, {lf_lon:.2f}°E)"

        return {
            "available": True,
            "n_timesteps": nt,
            "time_metadata": {
                "units": t_units,
                "calendar": t_calendar,
                "model_start_time_iso": iso_dates[0],
                "exact_times_available": bool(iso_dates[0] and iso_dates[landfall_idx]),
                "source": "NetCDF time coordinate",
            },
            "current_state": {
                "time_iso": iso_dates[0],
                "wind_speed_kmh": round(cur_wind, 1),
                "category_imd_en": _imd_category_en(cur_wind),
                "center_lat": round(cur_lat, 2),
                "center_lon": round(cur_lon, 2),
                "location_label_bn": current_location_label,
                "location_label_en": current_location_label_en,
                "direction_bn": direction_bn,
                "direction_en": direction_en,
                "direction_deg": ang,
            },
            "forecast_state": {
                "time_iso": iso_dates[landfall_idx],
                "lead_time_hours": round(lead_hours, 1),
                "landfall_wind_kmh": round(lf_wind, 1),
                "category_imd_en": _imd_category_en(lf_wind),
                "landfall_lat": round(lf_lat, 2),
                "landfall_lon": round(lf_lon, 2),
                "landfall_place_bn": landfall_place,
                "landfall_place_en": landfall_place_en,
                "landfall_union": landfall_union,
                "landfall_upazila": landfall_upazila,
                "landfall_district": landfall_district,
                "landfall_detection_method": landfall_detection_method,
            },
            "track_points": [
                {
                    "t": t,
                    "lat": round(centers[t][0], 3) if np.isfinite(centers[t][0]) else None,
                    "lon": round(centers[t][1], 3) if np.isfinite(centers[t][1]) else None,
                    "wind_kmh": round(centers[t][2], 1),
                    "time_iso": iso_dates[t],
                }
                for t in range(nt)
            ],
        }
    except Exception as exc:  # noqa: BLE001 - fail soft
        print(f"[track] analyze_cyclone_track failed: {exc}", flush=True)
        return {"available": False}
    finally:
        if temp_path and os.path.exists(temp_path):
            _safe_remove(temp_path)


def _track_map_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Load a Unicode-capable local font, with a Pillow default fallback."""
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


_COMPLEX_TEXT_SUPPORTED: bool | None = None


def _complex_text_supported() -> bool:
    """True when Pillow can shape Indic scripts (i.e. was built with libraqm).

    Bengali needs OpenType shaping: pre-base vowel signs are stored *after*
    their consonant and must be reordered before them, and consonant clusters
    join into conjunct glyphs. Pillow only does that through libraqm; with the
    basic layout engine it draws the codepoints in logical order, so
    "বাতাসের গতি" comes out as "বাতাসরে গতি" and "মিটার" as "মটিার" — visibly
    misspelt Bengali. Callers fall back to the English label instead of
    printing something wrong.
    """
    global _COMPLEX_TEXT_SUPPORTED
    if _COMPLEX_TEXT_SUPPORTED is None:
        try:
            from PIL import features as _pil_features

            _COMPLEX_TEXT_SUPPORTED = bool(_pil_features.check("raqm"))
        except Exception:  # noqa: BLE001 - fail soft
            _COMPLEX_TEXT_SUPPORTED = False
        if not _COMPLEX_TEXT_SUPPORTED:
            print(
                "[map] Pillow was built without libraqm, so Bengali cannot be shaped "
                "correctly in rendered images — map labels fall back to English. "
                "To enable Bengali: `brew install libraqm` (or apt install libraqm-dev), "
                "then `pip install --force-reinstall --no-binary :all: pillow`.",
                flush=True,
            )
    return _COMPLEX_TEXT_SUPPORTED


def _bengali_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Bengali-capable font, preferred over the Latin-first default."""
    candidates = [
        "/System/Library/Fonts/Supplemental/Bangla Sangam MN.ttc",
        "/System/Library/Fonts/Supplemental/Bangla MN.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansBengali-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return _track_map_font(size, bold=bold)



AREA_MAP_METRICS = {
    "wind": {
        "column": "wind",
        "label_en": "Maximum wind speed (km/hr) — IMD class",
        "label_bn": "সর্বোচ্চ বাতাসের গতি (কিমি/ঘণ্টা) — IMD শ্রেণী",
        "unit": "km/h",
        "digits": 1,
        "scale": "imd",
    },
    "rainfall": {
        "column": "rain",
        "label_en": "Total rainfall (mm)",
        "label_bn": "মোট বৃষ্টিপাত (মিমি)",
        "unit": "mm",
        "digits": 1,
        "colors": ["#e8f5e9", "#a5d6a7", "#66bb6a", "#43a047", "#2e7d32", "#1b5e20"],
    },
    "surge": {
        "column": "surge",
        "label_en": "Storm surge (m)",
        "label_bn": "ঝড়জলোচ্ছ্বাস (মিটার)",
        "unit": "m",
        "digits": 2,
        "colors": ["#e0f7fa", "#80deea", "#26c6da", "#00acc1", "#00838f", "#006064"],
    },
    "risk": {
        "column": "risk",
        "label_en": "Risk class",
        "label_bn": "ঝুঁকি শ্রেণী",
        "unit": "",
        "digits": 0,
        "categorical": True,
        "colors": ["#2e7d32", "#9ccc65", "#ffd54f", "#fb8c00", "#c62828"],
    },
}


def build_visualization_export_table(table_classification: pd.DataFrame) -> pd.DataFrame:
    """Add display-only wind values to downloadable map/classification data.

    ``Wind Speed (km/h)`` stays untouched because it is the area-average
    modelling value used for risk, damage and affected-population outputs.
    The additional maximum field is the temporal-and-spatial peak used only
    for wind maps and for people recreating those maps from the exported data.
    """
    display = table_classification.copy()
    rename = {
        "Wind Speed (km/h)": "Average Wind Speed (km/h) [model]",
        "Peak Wind Speed (km/h)": "Maximum Wind Speed (km/h) [visualization]",
    }
    display = display.rename(columns={old: new for old, new in rename.items() if old in display.columns})
    return display

_RISK_ORDER = ["Very Low", "Low", "Medium", "High", "Very High"]

AREA_MAP_SUPERSAMPLE = 2


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _is_dark(hex_color: str) -> bool:
    """True when white text reads better than dark text on this fill.

    Uses the ITU-R BT.601 luma of the fill, so a label sitting on the deep end
    of a colour ramp flips to white instead of staying near-invisible navy.
    """
    try:
        r, g, b = _hex_to_rgb(hex_color)
    except (ValueError, IndexError):
        return False
    return (0.299 * r + 0.587 * g + 0.114 * b) < 145


def _ramp_color(fraction: float, colors: list[str]) -> str:
    """Pick a bucket colour for a 0..1 position along the ramp."""
    if not colors:
        return "#cccccc"
    if fraction != fraction:  # NaN
        return "#e0e0e0"
    idx = int(max(0.0, min(0.999, fraction)) * len(colors))
    return colors[min(idx, len(colors) - 1)]


def _area_metric_value(row: dict, metric: str) -> float | None:
    key = AREA_MAP_METRICS[metric]["column"]
    value = row.get(key)
    return value if isinstance(value, (int, float)) and not pd.isna(value) else None


def _fill_area_record_gaps(records: list[dict], max_passes: int = 4) -> int:
    """In-place neighbour fill for the area map's child polygons.

    Mirrors fill_map_gaps/fill_gaps_from_neighbours for the plain dict records
    the Pillow renderer works with: `value` (numeric) takes the neighbours'
    median, `risk` (categorical) their mode with ties going to the more severe
    class. Adjacency is computed from the polygons being drawn.
    """
    if not records:
        return 0
    needs_value = any(r["value"] is None for r in records)
    needs_risk = any(not r["risk"] for r in records)
    if not (needs_value or needs_risk):
        return 0

    geoms = [r["geometry"] for r in records]
    usable = [i for i, g in enumerate(geoms) if g is not None and not g.is_empty]
    if len(usable) < 2:
        return 0
    series = gpd.GeoSeries([geoms[i] for i in usable])
    left, right = series.sindex.query(series, predicate="intersects")
    adjacency: dict[int, list[int]] = {i: [] for i in usable}
    for a, b in zip(left, right):
        if a != b:
            adjacency[usable[a]].append(usable[b])

    rank = {name: i for i, name in enumerate(_RISK_ORDER)}
    filled = 0
    for _ in range(max_passes):
        resolved: dict[int, dict] = {}
        for i in usable:
            patch: dict = {}
            if records[i]["value"] is None:
                numbers = [
                    records[n]["value"] for n in adjacency[i] if records[n]["value"] is not None
                ]
                if numbers:
                    patch["value"] = float(statistics.median(numbers))
            if not records[i]["risk"]:
                classes = [records[n]["risk"] for n in adjacency[i] if records[n]["risk"]]
                if classes:
                    counts = Counter(classes)
                    top = max(counts.values())
                    tied = [v for v, c in counts.items() if c == top]
                    patch["risk"] = max(tied, key=lambda v: rank.get(v, -1))
            if patch:
                resolved[i] = patch
        if not resolved:
            break
        for i, patch in resolved.items():
            records[i].update(patch)
            filled += len(patch)
    return filled


def make_area_map_png(
    *,
    level: str,
    district: str,
    upazila: str,
    union: str,
    metric: str,
    geo_code: str = "",
    metrics_by_geo: dict,
    gdf_union_full: gpd.GeoDataFrame,
    gdf_upazila: gpd.GeoDataFrame,
    gdf_district: gpd.GeoDataFrame,
    output_path: str | Path,
    lang: str = "bn",
    scale: int = 2,
) -> Path | None:
    """Render one area-focused choropleth PNG.

    `level` selects what the map is centred on and what fills it:
      district -> that district's outline, filled with its upazilas
      upazila  -> that upazila's outline, filled with its unions
      union    -> that union alone
    """
    spec = AREA_MAP_METRICS.get(metric)
    if spec is None:
        return None

    def norm(value: object) -> str:
        """Normalise an administrative name for comparison.

        The BBS shapefiles store bare names ("Teknaf") while the analysis
        contexts append the level ("Teknaf Union"), so the suffix is stripped
        before comparing.
        """
        text = str(value or "").lower()
        text = re.sub(r"\b(union|paurashava|pourashava|city\s*corporation)\b", " ", text)
        return re.sub(r"[^a-z0-9]", "", text)

    geo = _safe_str(geo_code)

    outline: gpd.GeoDataFrame
    children: gpd.GeoDataFrame
    name_col: str
    if level == "district":
        outline = gdf_district[gdf_district["DISTRICT_NAME"].map(norm) == norm(district)]
        children = gdf_upazila[gdf_upazila["DISTRICT_NAME"].map(norm) == norm(district)]
        name_col = "UPAZILA_NAME"
        title_area = district
    elif level == "upazila":
        outline = gdf_upazila[
            (gdf_upazila["UPAZILA_NAME"].map(norm) == norm(upazila))
            & (gdf_upazila["DISTRICT_NAME"].map(norm) == norm(district) if district else True)
        ]
        children = gdf_union_full[
            (gdf_union_full["UPAZILA_NAME"].map(norm) == norm(upazila))
            & (gdf_union_full["DISTRICT_NAME"].map(norm) == norm(district) if district else True)
        ]
        name_col = "UNION_NAME"
        title_area = ", ".join([p for p in (upazila, district) if p])
    else:  # union — GEO_CODE is exact; fall back to name when it is absent
        if geo:
            children = gdf_union_full[gdf_union_full["GEO_CODE"].astype(str) == geo]
        else:
            children = gdf_union_full[
                (gdf_union_full["UNION_NAME"].map(norm) == norm(union))
                & (gdf_union_full["UPAZILA_NAME"].map(norm) == norm(upazila) if upazila else True)
            ]
        outline = children
        name_col = "UNION_NAME"
        title_area = ", ".join([p for p in (union, upazila, district) if p])

    if children is None or children.empty:
        print(f"[area-map] no child polygons for {level}/{district}/{upazila}/{union}", flush=True)
        return None

    records = []
    for _, row in children.iterrows():
        geo = _safe_str(row.get("GEO_CODE", ""))
        stats = metrics_by_geo.get(geo, {})
        records.append(
            {
                "geometry": row.geometry,
                "name": _safe_str(row.get(name_col, "")),
                "value": _area_metric_value(stats, metric),
                "risk": _safe_str(stats.get("risk", "")),
            }
        )

    _fill_area_record_gaps(records)

    categorical = bool(spec.get("categorical"))
    imd_scale = spec.get("scale") == "imd"
    if imd_scale:
        def color_for(rec: dict) -> str:
            idx = imd_wind_class_index(rec["value"])
            return IMD_NO_DATA_COLOR if idx is None else IMD_WIND_CLASSES[idx]["color"]

        legend_entries = [(imd_legend_label(c), c["color"]) for c in IMD_WIND_CLASSES]
    elif categorical:
        def color_for(rec: dict) -> str:
            try:
                idx = _RISK_ORDER.index(rec["risk"])
            except ValueError:
                return "#e0e0e0"
            return spec["colors"][min(idx, len(spec["colors"]) - 1)]
        legend_entries = [(r, spec["colors"][min(i, len(spec["colors"]) - 1)]) for i, r in enumerate(_RISK_ORDER)]
    else:
        values = [r["value"] for r in records if r["value"] is not None]
        vmin, vmax = (min(values), max(values)) if values else (0.0, 0.0)
        span = (vmax - vmin) or 1.0

        def color_for(rec: dict) -> str:
            if rec["value"] is None:
                return "#e0e0e0"
            return _ramp_color((rec["value"] - vmin) / span, spec["colors"])

        n = len(spec["colors"])
        legend_entries = [
            (
                f"{vmin + span * i / n:.{spec['digits']}f} – {vmin + span * (i + 1) / n:.{spec['digits']}f}",
                spec["colors"][i],
            )
            for i in range(n)
        ]

    base_w, base_h = 1000, 900
    out_w, out_h = base_w * scale, base_h * scale
    scale *= AREA_MAP_SUPERSAMPLE
    width, height = base_w * scale, base_h * scale
    legend_margin = 290 if (imd_scale or categorical) else 250
    m_left, m_right, m_top, m_bottom = 40 * scale, legend_margin * scale, 96 * scale, 46 * scale
    plot_w, plot_h = width - m_left - m_right, height - m_top - m_bottom

    minx, miny, maxx, maxy = children.total_bounds
    pad_x = (maxx - minx) * 0.06 or 0.02
    pad_y = (maxy - miny) * 0.06 or 0.02
    minx, maxx, miny, maxy = minx - pad_x, maxx + pad_x, miny - pad_y, maxy + pad_y
    lat_mid = (miny + maxy) / 2.0
    x_span = (maxx - minx) * math.cos(math.radians(lat_mid))
    y_span = maxy - miny
    fit = min(plot_w / x_span, plot_h / y_span) if x_span and y_span else 1.0
    draw_w, draw_h = x_span * fit, y_span * fit
    off_x = m_left + (plot_w - draw_w) / 2
    off_y = m_top + (plot_h - draw_h) / 2

    def xy(lon: float, lat: float) -> tuple[float, float]:
        return (
            off_x + (lon - minx) * math.cos(math.radians(lat_mid)) * fit,
            off_y + (maxy - lat) * fit,
        )

    bengali = lang != "en" and _complex_text_supported()
    metric_label = spec["label_bn"] if bengali else spec["label_en"]
    metric_font = _bengali_font if bengali else _track_map_font

    image = Image.new("RGB", (width, height), "#ffffff")
    draw = ImageDraw.Draw(image)
    f_title = metric_font(26 * scale, bold=True)
    f_sub = _track_map_font(15 * scale)
    f_legend = metric_font(14 * scale)
    f_legend_num = _track_map_font(14 * scale)
    f_label = _track_map_font(13 * scale)
    f_foot = _track_map_font(12 * scale)

    def rings(geom):
        if geom is None or geom.is_empty:
            return []
        polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        return [[xy(float(x), float(y)) for x, y in p.exterior.coords] for p in polys]

    for rec in records:
        fill = color_for(rec)
        for ring in rings(rec["geometry"]):
            if len(ring) >= 3:
                draw.polygon(ring, fill=fill)

    border_w = max(2, int(round(1.5 * scale)))
    for rec in records:
        for ring in rings(rec["geometry"]):
            if len(ring) >= 3:
                closed = ring + [ring[0]]
                draw.line(closed, fill="#ffffff", width=border_w + max(2, scale))
                draw.line(closed, fill="#1e293b", width=border_w)

    for _, row in outline.iterrows():
        for ring in rings(row.geometry):
            if len(ring) >= 3:
                draw.line(ring + [ring[0]], fill="#0f2740", width=max(2, 3 * scale))

    if len(records) <= 40:
        placed: list[tuple[float, float, float, float]] = []
        label_h = 16 * scale
        ordered = sorted(
            (r for r in records if r["geometry"] is not None and not r["geometry"].is_empty and r["name"]),
            key=lambda r: r["geometry"].area,
            reverse=True,
        )
        halo = max(2, int(round(0.9 * scale)))
        for rec in ordered:
            c = rec["geometry"].representative_point()
            cx, cy = xy(float(c.x), float(c.y))
            label = rec["name"]
            tw = draw.textlength(label, font=f_label)
            box = (cx - tw / 2, cy, cx + tw / 2, cy + label_h)
            if any(
                box[0] < p[2] and box[2] > p[0] and box[1] < p[3] and box[3] > p[1]
                for p in placed
            ):
                continue  # would overlap an already-placed label
            placed.append(box)
            dark_fill = _is_dark(color_for(rec))
            draw.text(
                (box[0], cy),
                label,
                fill="#ffffff" if dark_fill else "#12304a",
                font=f_label,
                stroke_width=halo,
                stroke_fill="#12304a" if dark_fill else "#ffffff",
            )

    level_word = {"district": "District", "upazila": "Upazila", "union": "Union"}.get(level, level.title())
    draw.text((m_left, 26 * scale), f"{title_area} — {metric_label}", fill="#102a43", font=f_title)
    child_word = {"district": "upazilas", "upazila": "unions", "union": "area"}[level]
    draw.text(
        (m_left, 64 * scale),
        f"{level_word} view · {len(records)} {child_word} · values from the uploaded forecast",
        fill="#486581",
        font=f_sub,
    )

    lx = width - m_right + 24 * scale
    ly = m_top
    draw.text((lx, ly), metric_label, fill="#102a43", font=f_legend)
    ly += 26 * scale
    for text, color in legend_entries:
        draw.rectangle([lx, ly, lx + 22 * scale, ly + 16 * scale], fill=color, outline="#94a3b8")
        draw.text((lx + 30 * scale, ly + 1 * scale), text, fill="#334155", font=f_legend_num)
        ly += 24 * scale
    if imd_scale:
        show_no_data = any(imd_wind_class_index(r["value"]) is None for r in records)
    elif categorical:
        show_no_data = any(not r["risk"] for r in records)
    else:
        show_no_data = any(r["value"] is None for r in records)
    if show_no_data:
        draw.rectangle([lx, ly, lx + 22 * scale, ly + 16 * scale], fill="#e0e0e0", outline="#94a3b8")
        draw.text((lx + 30 * scale, ly + 1 * scale), "No data", fill="#334155", font=f_legend_num)

    draw.text(
        (m_left, height - 30 * scale),
        "Source: uploaded NetCDF + bundled BBS 2022 boundaries (union / upazila / district).",
        fill="#486581",
        font=f_foot,
    )

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if (width, height) != (out_w, out_h):
        image = image.resize((out_w, out_h), Image.LANCZOS)
    image.save(out, format="PNG", optimize=True)
    return out


def make_track_map_jpg(
    cyclone_track: dict,
    gdf_upazila: gpd.GeoDataFrame,
    output_path: str | Path,
    cyclone_name: str | None = None,
) -> Path | None:
    """Draw a self-contained JPEG of the model-derived cyclone track.

    The map uses the bundled upazila polygons, so it has no dependency on an
    external tile server and remains reproducible/offline during emergencies.
    """
    if not cyclone_track.get("available"):
        return None
    points = [
        p
        for p in cyclone_track.get("track_points", [])
        if p.get("lat") is not None and p.get("lon") is not None
    ]
    if not points:
        return None

    width, height = 1500, 1500
    margin_left, margin_right, margin_top, margin_bottom = 105, 55, 115, 95
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom

    minx_bd, miny_bd, maxx_bd, maxy_bd = gdf_upazila.total_bounds
    lons = [float(p["lon"]) for p in points]
    lats = [float(p["lat"]) for p in points]
    min_lon = min(min(lons), float(minx_bd)) - 0.6
    max_lon = max(max(lons), float(maxx_bd)) + 0.6
    min_lat = min(min(lats), float(miny_bd)) - 0.6
    max_lat = max(max(lats), float(maxy_bd)) + 0.6

    def xy(lon: float, lat: float) -> tuple[int, int]:
        x = margin_left + int((lon - min_lon) / (max_lon - min_lon) * plot_w)
        y = margin_top + int((max_lat - lat) / (max_lat - min_lat) * plot_h)
        return x, y

    image = Image.new("RGB", (width, height), "#dff3ff")
    draw = ImageDraw.Draw(image)
    title_font = _track_map_font(34, bold=True)
    label_font = _track_map_font(23)
    small_font = _track_map_font(18)
    tiny_font = _track_map_font(15)

    for lon in range(int(math.floor(min_lon)), int(math.ceil(max_lon)) + 1):
        x, _ = xy(float(lon), min_lat)
        draw.line([(x, margin_top), (x, margin_top + plot_h)], fill="#b9d7e8", width=1)
        draw.text((x + 4, margin_top + plot_h + 12), f"{lon}°E", fill="#4b6472", font=tiny_font)
    for lat in range(int(math.floor(min_lat)), int(math.ceil(max_lat)) + 1):
        _, y = xy(min_lon, float(lat))
        draw.line([(margin_left, y), (margin_left + plot_w, y)], fill="#b9d7e8", width=1)
        draw.text((22, y - 10), f"{lat}°N", fill="#4b6472", font=tiny_font)

    for geom in gdf_upazila.geometry:
        if geom is None or geom.is_empty:
            continue
        polygons = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        for polygon in polygons:
            exterior = [xy(float(lon), float(lat)) for lon, lat in polygon.exterior.coords]
            if len(exterior) >= 3:
                draw.polygon(exterior, fill="#edf5df", outline="#78906c")

    track_xy = [xy(float(p["lon"]), float(p["lat"])) for p in points]
    if len(track_xy) > 1:
        draw.line(track_xy, fill="#164e91", width=7, joint="curve")

    for idx, (point, coord) in enumerate(zip(points, track_xy)):
        wind = float(point.get("wind_kmh") or 0.0)
        color = "#7f1d1d" if wind >= 167 else "#dc2626" if wind >= 118 else "#f59e0b" if wind >= 89 else "#2563eb"
        r = 8 if idx not in {0, len(points) - 1} else 11
        draw.ellipse([coord[0] - r, coord[1] - r, coord[0] + r, coord[1] + r], fill=color, outline="white", width=2)

    current = cyclone_track.get("current_state") or {}
    forecast = cyclone_track.get("forecast_state") or {}
    current_xy = xy(float(current.get("center_lon")), float(current.get("center_lat")))
    landfall_xy = xy(float(forecast.get("landfall_lon")), float(forecast.get("landfall_lat")))
    draw.ellipse([current_xy[0] - 15, current_xy[1] - 15, current_xy[0] + 15, current_xy[1] + 15], fill="#0f4c81", outline="white", width=4)
    draw.ellipse([landfall_xy[0] - 18, landfall_xy[1] - 18, landfall_xy[0] + 18, landfall_xy[1] + 18], fill="#b91c1c", outline="#ffffff", width=5)

    current_label = f"Current: {float(current.get('wind_speed_kmh') or 0):.1f} km/h"
    landfall_place = _safe_str(forecast.get("landfall_place_bn")) or "Forecast landfall"
    landfall_label = f"First on-land point: {landfall_place}"
    draw.rounded_rectangle(
        [current_xy[0] + 18, current_xy[1] - 38, current_xy[0] + 340, current_xy[1] + 2],
        radius=8,
        fill="#ffffff",
        outline="#0f4c81",
    )
    draw.text((current_xy[0] + 28, current_xy[1] - 31), current_label, fill="#0f2740", font=tiny_font)

    landfall_marker_r = 18
    label_h = 40
    label_box_width = min(560, max(330, int(len(landfall_label) * 8.4)))
    label_left = min(max(margin_left, landfall_xy[0] - label_box_width // 2), width - margin_right - label_box_width)
    label_bottom = landfall_xy[1] - landfall_marker_r - 18
    label_top = label_bottom - label_h
    if label_top < margin_top + 8:  # keep it inside the plot area
        label_top = margin_top + 8
        label_bottom = label_top + label_h
    draw.line(
        [(landfall_xy[0], landfall_xy[1] - landfall_marker_r), (landfall_xy[0], label_bottom)],
        fill="#b91c1c",
        width=2,
    )
    draw.rounded_rectangle(
        [label_left, label_top, label_left + label_box_width, label_bottom],
        radius=8,
        fill="#ffffff",
        outline="#b91c1c",
    )
    draw.text((label_left + 12, label_top + 11), landfall_label, fill="#5f1515", font=tiny_font)

    title = f"{cyclone_name or 'Cyclone'} — model-derived forecast track"
    draw.text((margin_left, 35), title, fill="#102a43", font=title_font)
    lead = forecast.get("lead_time_hours")
    subtitle = (
        f"First forecast-grid centre over Bangladesh land: +{float(lead):.0f} h | "
        "Track centre = wind-weighted centroid of strongest 0.5% of cells"
        if lead is not None
        else "Track centre = wind-weighted centroid of strongest 0.5% of cells"
    )
    draw.text((margin_left, 78), subtitle, fill="#486581", font=small_font)
    draw.text(
        (margin_left, height - 48),
        "Source: uploaded NetCDF + bundled Bangladesh upazila boundaries. Times and positions retain model resolution.",
        fill="#486581",
        font=tiny_font,
    )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="JPEG", quality=94, optimize=True)
    return output


def process_cyclone(
    nc_path: str | Path,
    output_dir: str | Path | None = None,
    data_dir: str | Path | None = None,
    polished: bool = True,
    rainfall_path: str | Path | None = None,
    storm_surge_path: str | Path | None = None,
    damage_model: str = "ccm",
    cyclone_name: str | None = None,
    preloaded: dict | None = None,
) -> dict:
    """Run the cyclone analysis pipeline for NetCDF or direct CSV/XLSX input.

    Parameters
    ----------
    nc_path : str | Path
        Wind-speed input: NetCDF, CSV, XLSX, or XLS.
    rainfall_path : str | Path, optional
        Independent rainfall input: NetCDF, CSV, XLSX, or XLS. When omitted,
        rainfall embedded in the wind NetCDF remains supported for backwards
        compatibility.
    output_dir : str | Path, optional
        Directory where outputs will be written. If omitted, a temporary
        directory is created.
    data_dir : str | Path, optional
        Directory containing the static household Excel and shapefile assets.
        Defaults to the folder containing this script.
    polished : bool, default True
        Whether to attempt LLM-based polishing of the Bengali guideline.
    preloaded : dict, optional
        A bundle produced by ``load_all_gis_data()`` (optionally passed
        through ``copy_gis_bundle()`` by the caller). When provided, the
        expensive shapefile read + reprojection step is skipped entirely —
        this is how ``service.py`` serves requests without re-loading ~80MB
        of GIS assets every time. When omitted, data is loaded fresh from
        ``data_dir`` (unchanged CLI/standalone behaviour).

    Returns
    -------
    dict
        Manifest describing generated artifacts and summary statistics.
    """
    import time
    
    t_start = time.time()
    print(f"[TIMING] Pipeline started", flush=True)

    input_path = Path(nc_path).expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Forecast file not found: {input_path}")
    input_type = "tabular" if input_path.suffix.lower() in TABULAR_FORECAST_EXTENSIONS else "netcdf"
    if input_type == "netcdf" and input_path.suffix.lower() != ".nc":
        raise ValueError("Forecast file must be .nc, .csv, or .xlsx.")

    rainfall_input_path = Path(rainfall_path).expanduser().resolve() if rainfall_path else None
    if rainfall_input_path is not None:
        if not rainfall_input_path.exists():
            raise FileNotFoundError(f"Rainfall file not found: {rainfall_input_path}")
        if rainfall_input_path.suffix.lower() not in {".nc", *TABULAR_FORECAST_EXTENSIONS}:
            raise ValueError("Rainfall file must be .nc, .csv, .xlsx, or .xls.")

    data_path = _resolve_data_dir(data_dir)

    if output_dir is None:
        output_path = Path(tempfile.mkdtemp(prefix="cyclone-output-"))
        created_temp_dir = True
    else:
        output_path = Path(output_dir).expanduser().resolve()
        output_path.mkdir(parents=True, exist_ok=True)
        created_temp_dir = False

    t0 = time.time()
    if preloaded is not None:
        data_path = preloaded.get("data_path", data_path)
        df_percent = preloaded["df_percent"]
        df_number = preloaded["df_number"]
        gdf_union = preloaded["gdf_union"]
        gdf_union_full = preloaded["gdf_union_full"]
        gdf_upazila = preloaded["gdf_upazila"]
        gdf_district = preloaded["gdf_district"]
        gdf_union_map = preloaded.get("gdf_union_map", gdf_union)
        gdf_upazila_map = preloaded.get("gdf_upazila_map", gdf_upazila)
        print(f"[TIMING] Using preloaded GIS data (cache hit): {time.time()-t0:.3f}s", flush=True)
    else:
        df_percent, df_number, gdf_union, gdf_union_full = load_household_data(
            housing_excel_path=str(data_path / "union_bbs.csv"),
            shp_path=str(data_path / UNION_2022_SHP),
            legacy_shp_path=str(data_path / LEGACY_UNION_SHP),
        )
        gdf_upazila = load_upazila_shapefile(str(data_path / UPAZILA_2022_SHP))
        gdf_district = load_district_shapefile(str(data_path / DISTRICT_2022_SHP))
        gdf_union_map = _simplify_for_maps(gdf_union)
        gdf_upazila_map = _simplify_for_maps(gdf_upazila)
        print(f"[TIMING] load_household_data + load_upazila_shapefile (cold): {time.time()-t0:.2f}s", flush=True)

    nc_bytes: bytes | None = None
    storm_df: pd.DataFrame | None = None
    storm_upazila_df: pd.DataFrame | None = None
    storm_bytes: bytes | None = None
    input_metadata: dict = {"input_type": input_type}
    storm_input_path = Path(storm_surge_path).expanduser().resolve() if storm_surge_path else None
    if storm_input_path is not None:
        if not storm_input_path.exists():
            raise FileNotFoundError(f"Storm-surge file not found: {storm_input_path}")
        if storm_input_path.suffix.lower() not in {".nc", *TABULAR_FORECAST_EXTENSIONS}:
            raise ValueError("Storm-surge file must be .nc, .csv, .xlsx, or .xls.")
    if storm_input_path and storm_input_path.suffix.lower() == ".nc":
        with storm_input_path.open("rb") as f_surge:
            storm_bytes = f_surge.read()

    model_normalized = (damage_model or "ccm").lower()
    if model_normalized not in {"safir", "ccm"}:
        raise ValueError("damage_model must be either 'safir' or 'ccm'")

    t0_parse = time.time()
    if input_type == "tabular":
        print("[TABULAR] Reading direct union forecast rows...", flush=True)
        final_df_full, upazila_df, input_metadata = parse_tabular_forecast(
            input_path, gdf_union_full, gdf_upazila
        )

        bridge = final_df_full[["GEO_CODE", "BOUNDARY_GEO_CODE"]].copy()
        bridge = bridge[bridge["BOUNDARY_GEO_CODE"].fillna("").astype(str).str.strip() != ""]

        def rekey_housing(source: pd.DataFrame) -> pd.DataFrame:
            if bridge.empty or source.empty:
                return source.iloc[0:0].copy()
            joined = bridge.merge(
                source,
                left_on="BOUNDARY_GEO_CODE",
                right_on="GEO_CODE",
                how="inner",
                suffixes=("_analysis", "_source"),
            )
            joined["GEO_CODE"] = joined["GEO_CODE_analysis"]
            return joined[[column for column in source.columns if column in joined.columns]].copy()

        df_percent = rekey_housing(df_percent)
        df_number = rekey_housing(df_number)
        print(
            f"[TIMING] Parsed tabular input: {time.time()-t0_parse:.2f}s "
            f"({len(final_df_full)} available areas)",
            flush=True,
        )
    else:
        with input_path.open("rb") as f:
            nc_bytes = f.read()
        print("[PARALLEL] Starting parallel NetCDF parsing...", flush=True)

        def parse_union():
            return parse_netcdf(nc_bytes, gdf_union_full)

        def parse_upazila():
            return parse_netcdf_upazila(nc_bytes, gdf_upazila)

        def parse_surge_union():
            return parse_storm_surge(storm_bytes, gdf_union_full) if storm_bytes else None

        def parse_surge_upazila():
            return parse_storm_surge_upazila(storm_bytes, gdf_upazila) if storm_bytes else None

        with ThreadPoolExecutor(max_workers=4) as parse_executor:
            future_union = parse_executor.submit(parse_union)
            future_upazila = parse_executor.submit(parse_upazila)
            future_surge_union = parse_executor.submit(parse_surge_union)
            future_surge_upazila = parse_executor.submit(parse_surge_upazila)
            final_df_full = future_union.result()
            upazila_df = future_upazila.result()
            storm_df = future_surge_union.result()
            storm_upazila_df = future_surge_upazila.result()

        if storm_upazila_df is not None:
            upazila_df = upazila_df.merge(
                storm_upazila_df[["GEO_CODE", "max_storm_surge_m"]], on="GEO_CODE", how="left"
            )
        else:
            upazila_df["max_storm_surge_m"] = np.nan
        if storm_df is not None:
            final_df_full = final_df_full.merge(
                storm_df[["GEO_CODE", "max_storm_surge_m"]], on="GEO_CODE", how="left"
            )
        else:
            final_df_full["max_storm_surge_m"] = np.nan
        print(f"[TIMING] All NetCDF parsing (parallel): {time.time()-t0_parse:.2f}s", flush=True)

        wind_time_meta = read_netcdf_time_metadata(nc_bytes) if nc_bytes else {"available": False}
        if wind_time_meta.get("available"):
            try:
                span_hours = (
                    pd.Timestamp(wind_time_meta["end_time_iso"])
                    - pd.Timestamp(wind_time_meta["start_time_iso"])
                ).total_seconds() / 3600.0
                used_hours = min(span_hours, RAINFALL_ACCUMULATION_TARGET_HOURS)
                if used_hours > 0:
                    input_metadata["rainfall_accumulation_hours"] = round(used_hours, 1)
                    input_metadata["rainfall_target_hours"] = RAINFALL_ACCUMULATION_TARGET_HOURS
                    input_metadata["forecast_start_iso"] = wind_time_meta["start_time_iso"]
                    input_metadata["forecast_end_iso"] = wind_time_meta["end_time_iso"]
                    print(
                        f"[rainfall] accumulation window = {used_hours:.0f} h of a "
                        f"{RAINFALL_ACCUMULATION_TARGET_HOURS:.0f} h target "
                        f"(file spans {span_hours:.0f} h: "
                        f"{wind_time_meta['start_time_iso']} -> {wind_time_meta['end_time_iso']})",
                        flush=True,
                    )
                input_metadata["rainfall_file_span_hours"] = round(span_hours, 1)
            except Exception as exc:  # noqa: BLE001 - metadata only
                print(f"[rainfall] could not derive accumulation window: {exc}", flush=True)

    def replace_hazard_metric(
        target: pd.DataFrame,
        source: pd.DataFrame,
        column: str,
    ) -> pd.DataFrame:
        """Replace one weather field without changing the modelling fields."""
        return (
            target.drop(columns=[column], errors="ignore")
            .merge(source[["GEO_CODE", column]].drop_duplicates("GEO_CODE"), on="GEO_CODE", how="left")
        )

    if rainfall_input_path is not None:
        if rainfall_input_path.suffix.lower() == ".nc":
            rain_union = parse_rainfall_netcdf(rainfall_input_path, gdf_union_full)
            rain_upazila = parse_rainfall_netcdf(rainfall_input_path, gdf_upazila)
            rain_source_type = "netcdf"
        else:
            rain_union, rain_upazila, _ = parse_tabular_hazard(
                rainfall_input_path, "rainfall", gdf_union_full, gdf_upazila
            )
            rain_source_type = "tabular"
        final_df_full = replace_hazard_metric(final_df_full, rain_union, "max_total_rainfall")
        upazila_df = replace_hazard_metric(upazila_df, rain_upazila, "max_total_rainfall")
        input_metadata["rainfall_source"] = rain_source_type
        input_metadata["rainfall_filename"] = rainfall_input_path.name

    if storm_input_path is not None and not (
        input_type == "netcdf" and storm_input_path.suffix.lower() == ".nc"
    ):
        if storm_input_path.suffix.lower() == ".nc":
            storm_union = parse_storm_surge(storm_input_path, gdf_union_full)
            storm_upazila = parse_storm_surge_upazila(storm_input_path, gdf_upazila)
            storm_source_type = "netcdf"
        else:
            storm_union, storm_upazila, _ = parse_tabular_hazard(
                storm_input_path, "surge", gdf_union_full, gdf_upazila
            )
            storm_source_type = "tabular"
        final_df_full = replace_hazard_metric(final_df_full, storm_union, "max_storm_surge_m")
        upazila_df = replace_hazard_metric(upazila_df, storm_upazila, "max_storm_surge_m")
        input_metadata["storm_surge_source"] = storm_source_type
        input_metadata["storm_surge_filename"] = storm_input_path.name

    final_df_full = final_df_full.drop_duplicates(subset=["GEO_CODE"])

    final_df = final_df_full.copy()
    final_df = final_df.drop_duplicates(subset=["GEO_CODE"])
    if "max_storm_surge_m" not in final_df.columns:
        final_df["max_storm_surge_m"] = np.nan

    t0 = time.time()
    risk_df, table_classification = classify_risk(final_df, df_percent, df_number)
    if input_type == "tabular":
        uploaded_names = final_df.set_index("GEO_CODE")
        for frame in (risk_df, table_classification):
            frame["Union"] = frame["GEO_CODE"].map(uploaded_names["UNION_NAME"]).fillna(frame["Union"])
            frame["Upazila"] = frame["GEO_CODE"].map(uploaded_names["UPAZILA_NAME"]).fillna(frame["Upazila"])
            district_column = "District" if "District" in frame.columns else "DISTRICT_NAME"
            frame[district_column] = frame["GEO_CODE"].map(uploaded_names["DISTRICT_NAME"]).fillna(frame[district_column])
    print(f"[TIMING] classify_risk: {time.time()-t0:.2f}s", flush=True)
    
    t0 = time.time()
    table_damage = build_damage_table(table_classification, damage_model=model_normalized)
    print(f"[TIMING] build_damage_table: {time.time()-t0:.2f}s", flush=True)

    t0 = time.time()
    table_classification = attach_affected_population_risk(
        table_classification,
        data_path,
        partial_coverage=input_type == "tabular",
    )

    table_classification, gap_fills = fill_gaps_from_neighbours(
        table_classification,
        gdf_union_full,
        numeric_columns=("Wind Speed (km/h)", "Total Rainfall (mm)", "Storm Surge (m)"),
        categorical_columns=("Risk",),
    )
    if gap_fills:
        print(
            "[gap-fill] estimated from neighbouring unions: "
            + ", ".join(f"{col}={n}" for col, n in gap_fills.items()),
            flush=True,
        )

    risk_df = table_classification.copy()
    if not table_damage.empty:
        table_damage = table_damage.merge(
            table_classification[["GEO_CODE", "Risk"]],
            on="GEO_CODE",
            how="left",
        )
    print(f"[TIMING] affected_population_risk: {time.time()-t0:.2f}s", flush=True)
    
    t0 = time.time()
    table_rainfall_evac = build_rainfall_evac_table(table_classification)
    print(f"[TIMING] build_rainfall_evac_table: {time.time()-t0:.2f}s", flush=True)

    table_visualization_export = build_visualization_export_table(table_classification)
    
    t0_parallel = time.time()
    print(f"[PARALLEL] Starting parallel Excel exports and map generation...", flush=True)
    
    map_tasks = []
    
    excel_results = {}
    with ThreadPoolExecutor(max_workers=4) as excel_executor:
        excel_futures = {
            excel_executor.submit(
                export_classification_excel,
                table_visualization_export,
                output_path / "risk_classification.xlsx"
            ): "classification_excel",
            excel_executor.submit(
                export_damage_excel,
                table_damage,
                output_path / "housing_damage.xlsx"
            ): "damage_excel",
            excel_executor.submit(
                export_rainfall_evac_excel,
                table_rainfall_evac,
                output_path / "rainfall_evacuation.xlsx"
            ): "rainfall_excel",
            excel_executor.submit(
                export_gis_map_excel,
                risk_df,
                upazila_df,
                table_visualization_export,
                table_damage,
                gdf_union,
                gdf_upazila,
                output_path / "gis_map.xlsx"
            ): "gis_map_excel",
        }
        for future in as_completed(excel_futures):
            name = excel_futures[future]
            try:
                excel_results[name] = future.result()
            except Exception as e:
                print(f"[PARALLEL] Excel export {name} failed: {e}", flush=True)
                excel_results[name] = None
    
    print(f"[TIMING] Excel exports (parallel): {time.time()-t0_parallel:.2f}s", flush=True)
    
    t0_maps = time.time()
    map_results = {
        "risk_map": None,
        "wind_intensity_map": None,
        "storm_surge_map": None,
        "rainfall_risk_map": None,
    }
    
    def safe_make_risk_map():
        try:
            return make_risk_map(risk_df, gdf_union_map, output_path / "risk_map.html")
        except Exception as e:
            print(f"[PARALLEL] risk_map error: {e}", flush=True)
            return None

    def safe_make_wind_map():
        try:
            return make_wind_intensity_map(
                upazila_df,
                gdf_upazila_map,
                output_path / "wind_intensity_map.html",
            )
        except Exception as e:
            print(f"[PARALLEL] wind_intensity_map error: {e}", flush=True)
            return None

    def safe_make_surge_map():
        try:
            return make_storm_surge_map(
                upazila_df,
                gdf_upazila_map,
                output_path / "storm_surge_map.html",
            )
        except Exception as e:
            print(f"[PARALLEL] storm_surge_map error: {e}", flush=True)
            return None

    def safe_make_rainfall_map():
        try:
            return make_rainfall_risk_map(
                upazila_df,
                gdf_upazila_map,
                output_path / "rainfall_risk_map.html",
            )
        except Exception as e:
            print(f"[PARALLEL] rainfall_risk_map error: {e}", flush=True)
            return None
    
    with ThreadPoolExecutor(max_workers=5) as map_executor:
        map_futures = {
            map_executor.submit(safe_make_risk_map): "risk_map",
            map_executor.submit(safe_make_wind_map): "wind_intensity_map",
            map_executor.submit(safe_make_surge_map): "storm_surge_map",
            map_executor.submit(safe_make_rainfall_map): "rainfall_risk_map",
        }
        for future in as_completed(map_futures):
            name = map_futures[future]
            try:
                map_results[name] = future.result()
                print(f"[PARALLEL] {name} completed", flush=True)
            except Exception as e:
                print(f"[PARALLEL] {name} failed: {e}", flush=True)
                map_results[name] = None
    
    print(f"[TIMING] All maps (parallel): {time.time()-t0_maps:.2f}s", flush=True)
    print(f"[TIMING] Total parallel section: {time.time()-t0_parallel:.2f}s", flush=True)
    
    map_html = map_results["risk_map"]
    wind_intensity_map_path = map_results["wind_intensity_map"]
    storm_surge_map_path = map_results["storm_surge_map"]
    rainfall_risk_map_path = map_results["rainfall_risk_map"]

    t0 = time.time()
    overall_damaged_types, class_info = summarise_damage_and_risk(table_damage)
    per_union_contexts = build_union_contexts(
        table_classification=table_classification,
        table_damage=table_damage,
        table_rainfall_evac=table_rainfall_evac,
        data_path=data_path,
        partial_coverage=input_type == "tabular",
    )
    per_upazila_contexts = build_full_upazila_contexts(per_union_contexts, upazila_df)
    per_district_contexts = build_aggregate_contexts(per_upazila_contexts, "district")
    per_district_contexts = enrich_district_contexts_from_boundaries(
        per_district_contexts,
        gdf_district,
    )

    per_union_contexts_light: list[dict] = []
    for ctx in per_union_contexts:
        light = {k: v for k, v in ctx.items() if k != "material_needs"}
        per_union_contexts_light.append(light)
    print(
        f"[TIMING] build hierarchy contexts: {time.time()-t0:.2f}s "
        f"({len(per_union_contexts_light)} unions, {len(per_upazila_contexts)} upazilas, "
        f"{len(per_district_contexts)} districts)",
        flush=True,
    )

    t0 = time.time()
    guideline = build_guideline(
        table_classification=table_classification,
        table_damage=table_damage,
        table_rainfall_evac=table_rainfall_evac,
        overall_damage_types=overall_damaged_types,
        class_info=class_info,
        polished=polished,
    )
    print(f"[TIMING] build_guideline: {time.time()-t0:.2f}s", flush=True)

    t0 = time.time()
    guideline_path = output_path / "guideline.md"
    guideline_path.write_text(guideline, encoding="utf-8")

    classification_csv_path = output_path / "risk_classification.csv"
    table_visualization_export.to_csv(classification_csv_path, index=False)

    damage_csv_path = output_path / "housing_damage.csv"
    table_damage.to_csv(damage_csv_path, index=False)

    rainfall_csv_path = output_path / "rainfall_evacuation.csv"
    table_rainfall_evac.to_csv(rainfall_csv_path, index=False)

    area_metrics_path = output_path / "area_metrics.json"
    area_metrics: dict[str, dict] = {}
    for _, row in table_classification.iterrows():
        geo = _safe_str(row.get("GEO_CODE", ""))
        if not geo:
            continue
        metrics = {
            "wind": _safe_float(row.get("Peak Wind Speed (km/h)")),
            "rain": _safe_float(row.get("Total Rainfall (mm)")),
            "surge": _safe_float(row.get("Storm Surge (m)")),
            "risk": _safe_str(row.get("Risk", "")),
        }
        area_metrics[geo] = metrics
        boundary_geo = _safe_str(row.get("Boundary GEO_CODE", ""))
        if boundary_geo:
            area_metrics[boundary_geo] = metrics
    if upazila_df is not None and not upazila_df.empty:
        for _, row in upazila_df.iterrows():
            geo = _safe_str(row.get("GEO_CODE", ""))
            if not geo:
                continue
            area_metrics[geo] = {
                "wind": _safe_float(row.get("peak_ws_kmh")),
                "rain": _safe_float(row.get("max_total_rainfall")),
                "surge": _safe_float(row.get("max_storm_surge_m")),
                "risk": "",
            }
    for ctx in per_upazila_contexts:
        geo = _safe_str(ctx.get("geo_code", ""))
        risk = _safe_str(ctx.get("risk", ""))
        if geo and risk and geo in area_metrics:
            area_metrics[geo]["risk"] = risk

    if upazila_df is not None and not upazila_df.empty:
        upazila_codes = [
            code
            for code in (_safe_str(row.get("GEO_CODE", "")) for _, row in upazila_df.iterrows())
            if code and code in area_metrics
        ]
        if upazila_codes:
            upazila_risk = pd.DataFrame(
                {
                    "GEO_CODE": upazila_codes,
                    "Risk": [area_metrics[code].get("risk", "") for code in upazila_codes],
                }
            )
            upazila_risk, upazila_fills = fill_gaps_from_neighbours(
                upazila_risk, gdf_upazila, categorical_columns=("Risk",)
            )
            if upazila_fills:
                for _, row in upazila_risk.iterrows():
                    code = _safe_str(row.get("GEO_CODE", ""))
                    if code in area_metrics:
                        area_metrics[code]["risk"] = _safe_str(row.get("Risk", ""))
                filled = upazila_fills.get("Risk", 0)
                print(f"[gap-fill] upazila risk estimated from neighbours: {filled}", flush=True)
                gap_fills["Risk (upazila)"] = filled

    area_metrics_path.write_text(json.dumps(area_metrics), encoding="utf-8")
    print(f"[TIMING] CSV/MD file writes: {time.time()-t0:.2f}s", flush=True)

    t0 = time.time()
    max_wind = table_classification["Wind Speed (km/h)"].max()
    max_rainfall = table_classification["Total Rainfall (mm)"].max()
    storm_col = "Storm Surge (m)" if "Storm Surge (m)" in table_classification.columns else None
    max_storm_surge = table_classification[storm_col].max() if storm_col else np.nan

    sorted_by_risk = table_classification.sort_values(
        "Affected Population (%)", ascending=False, na_position="last"
    )
    top_risk_extended: list[dict] = []
    for _, row in sorted_by_risk.head(10).iterrows():
        upazila_name = _safe_str(row.get("Upazila", ""))
        union_name = _safe_str(row.get("Union", ""))
        display_name = f"{union_name} ({upazila_name})" if upazila_name else union_name
        top_risk_extended.append(
            {
                "union": display_name,
                "upazila": _safe_str(row.get("Upazila", "")) or display_name,  # Backward compat
                "district": _safe_str(row.get("District", "")),
                "risk": _safe_str(row.get("Risk", "")),
                "affected_population_pct": _safe_float(row.get("Affected Population (%)")),
                "wind_speed_kmh": _safe_float(row.get("Wind Speed (km/h)")),
            }
        )

    sorted_by_rain = table_classification.sort_values(
        "Total Rainfall (mm)", ascending=False, na_position="last"
    )
    top_rain_extended: list[dict] = []
    for _, row in sorted_by_rain.head(10).iterrows():
        upazila_name = _safe_str(row.get("Upazila", ""))
        union_name = _safe_str(row.get("Union", ""))
        display_name = f"{union_name} ({upazila_name})" if upazila_name else union_name
        top_rain_extended.append(
            {
                "union": display_name,
                "upazila": _safe_str(row.get("Upazila", "")) or display_name,  # Backward compat
                "district": _safe_str(row.get("District", "")),
                "total_rainfall_mm": _safe_float(row.get("Total Rainfall (mm)")),
                "risk": _safe_str(row.get("Risk", "")),
            }
        )

    max_wind_record = None
    if table_classification["Wind Speed (km/h)"].notna().any():
        idx_wind = table_classification["Wind Speed (km/h)"].idxmax()
        max_row = table_classification.loc[idx_wind]
        max_wind_record = {
            "name": _safe_str(max_row.get("Union", "")),
            "union": _safe_str(max_row.get("Union", "")),
            "upazila": _safe_str(max_row.get("Upazila", "")) or _safe_str(max_row.get("Union", "")),
            "district": _safe_str(max_row.get("District", "")),
            "wind_speed_kmh": _safe_float(max_row.get("Wind Speed (km/h)")),
        }

    max_rain_record = None
    if table_classification["Total Rainfall (mm)"].notna().any():
        idx_rain = table_classification["Total Rainfall (mm)"].idxmax()
        max_rain_row = table_classification.loc[idx_rain]
        max_rain_record = {
            "name": _safe_str(max_rain_row.get("Union", "")),
            "union": _safe_str(max_rain_row.get("Union", "")),
            "upazila": _safe_str(max_rain_row.get("Upazila", "")) or _safe_str(max_rain_row.get("Union", "")),
            "district": _safe_str(max_rain_row.get("District", "")),
            "total_rainfall_mm": _safe_float(max_rain_row.get("Total Rainfall (mm)")),
        }
    max_storm_surge_record = None
    if storm_col and table_classification[storm_col].notna().any():
        idx_surge = table_classification[storm_col].idxmax()
        max_surge_row = table_classification.loc[idx_surge]
        max_storm_surge_record = {
            "name": _safe_str(max_surge_row.get("Union", "")),
            "union": _safe_str(max_surge_row.get("Union", "")),
            "upazila": _safe_str(max_surge_row.get("Upazila", "")) or _safe_str(max_surge_row.get("Union", "")),
            "district": _safe_str(max_surge_row.get("District", "")),
            "storm_surge_m": _safe_float(max_surge_row.get(storm_col)),
        }
    top_risk_names = [entry.get("union") or entry.get("upazila") for entry in top_risk_extended if entry.get("union") or entry.get("upazila")]
    top_rain_names = [entry.get("union") or entry.get("upazila") for entry in top_rain_extended if entry.get("union") or entry.get("upazila")]

    t0_track = time.time()
    cyclone_track = (
        analyze_cyclone_track(nc_bytes, gdf_union_full, cyclone_name)
        if nc_bytes is not None
        else {
            "available": False,
            "reason": "Cyclone track is unavailable for direct CSV/Excel area input.",
        }
    )
    if cyclone_track.get("available"):
        fs = cyclone_track.setdefault("forecast_state", {})
        fs["max_storm_surge_m"] = float(max_storm_surge) if pd.notna(max_storm_surge) else None
        fs["max_rainfall_mm"] = float(max_rainfall) if pd.notna(max_rainfall) else None
        fs["max_land_wind_kmh"] = float(max_wind) if pd.notna(max_wind) else None
        fs["max_wind_record"] = max_wind_record
        fs["max_rain_record"] = max_rain_record
        fs["max_storm_surge_record"] = max_storm_surge_record
        if pd.notna(max_wind):
            fs["category_imd_en"] = _imd_category_en(float(max_wind))

    data_quality_warnings: list[str] = []
    data_quality_warnings_en: list[str] = []
    if input_type == "tabular":
        rainfall_note_bn = (
            f"বৃষ্টিপাত ফাইলের “{TABULAR_RAINFALL_COLUMN}” কলাম থেকে নেওয়া হয়েছে "
            f"({RAINFALL_ACCUMULATION_TARGET_HOURS:.0f} ঘণ্টার সঞ্চিত মান)।"
            if input_metadata.get("rainfall_supplied")
            else f"ফাইলে “{TABULAR_RAINFALL_COLUMN}” কলাম নেই, তাই বৃষ্টিপাত ০ হিসেবে সংরক্ষিত হয়েছে।"
        )
        rainfall_note_en = (
            f"Rainfall is taken from the file's \u201c{TABULAR_RAINFALL_COLUMN}\u201d column "
            f"(a {RAINFALL_ACCUMULATION_TARGET_HOURS:.0f}-hour accumulation)."
            if input_metadata.get("rainfall_supplied")
            else f"The file has no \u201c{TABULAR_RAINFALL_COLUMN}\u201d column, so rainfall was stored as 0."
        )
        data_quality_warnings.append(
            "CSV/Excel ইনপুটে শুধু আপলোড করা ইউনিয়ন, উপজেলা ও জেলাগুলো নির্বাচন করা যাবে; "
            f"ফাইলে অনুপস্থিত এলাকা উপলভ্য নয়। {rainfall_note_bn} "
            "ঝুঁকি শুধু ক্ষতিগ্রস্ত জনসংখ্যার শতাংশ থেকে নির্ধারিত।"
        )
        data_quality_warnings_en.append(
            "CSV/Excel mode exposes only the unions, upazilas, and districts present in the uploaded file; "
            f"areas absent from the file are unavailable. {rainfall_note_en} "
            "Risk is derived only from affected population percentage."
        )
        unmatched_rows = int(input_metadata.get("unmatched_rows") or 0)
        if unmatched_rows:
            data_quality_warnings.append(
                f"{unmatched_rows}টি পুরোনো Union_Geo/নাম BBS 2022 সীমানার সাথে একভাবে মেলেনি। "
                "এলাকাগুলো নির্বাচনযোগ্য রাখা হয়েছে, তবে তাদের মানচিত্র বা BBS 2022 আবাসন/জনসংখ্যা তথ্য সীমিত হতে পারে।"
            )
            data_quality_warnings_en.append(
                f"{unmatched_rows} uploaded legacy areas did not have a unique BBS 2022 boundary match. "
                "They remain selectable, but boundary maps or BBS 2022 housing/population enrichment may be unavailable for them."
            )
    if gap_fills:
        filled_total = sum(gap_fills.values())
        filled_cols = ", ".join(sorted(gap_fills))
        data_quality_warnings.append(
            f"{filled_total}টি ফাঁকা ঘর ({filled_cols}) পার্শ্ববর্তী ইউনিয়নের মান থেকে অনুমান করে পূরণ করা "
            "হয়েছে, যাতে মানচিত্রে ফাঁকা অংশ না থাকে। সাধারণত এসব এলাকায় BBS 2022 অনুযায়ী কোনো "
            "জনসংখ্যা নেই (নদীর চর, সংরক্ষিত বন), তাই জনসংখ্যা-ভিত্তিক ঝুঁকি হিসাব করা যায় না। "
            "এই মানগুলো পূর্বাভাস নয়, প্রতিবেশী এলাকার ভিত্তিতে অনুমান।"
        )
        data_quality_warnings_en.append(
            f"{filled_total} blank cells ({filled_cols}) were estimated from adjoining unions so the "
            "maps have no gaps. These areas typically have zero BBS 2022 population (river chars, "
            "reserved forest), which leaves population-denominated risk undefined. The filled values "
            "are inferred from neighbours, not forecast for those areas."
        )

    file_span = _safe_float(input_metadata.get("rainfall_file_span_hours"))
    used_hours = _safe_float(input_metadata.get("rainfall_accumulation_hours"))
    if file_span is not None and used_hours is not None and file_span < RAINFALL_ACCUMULATION_TARGET_HOURS:
        data_quality_warnings.append(
            f"বৃষ্টিপাত {RAINFALL_ACCUMULATION_TARGET_HOURS:.0f} ঘণ্টার সঞ্চিত মান হিসেবে দেখানোর কথা, "
            f"কিন্তু আপলোড করা NetCDF ফাইলে মাত্র {file_span:.0f} ঘণ্টার পূর্বাভাস আছে। তাই দেখানো মান "
            f"{used_hours:.0f} ঘণ্টার সঞ্চিত বৃষ্টিপাত — এটি অনুমান করে বাড়ানো হয়নি। পূর্ণ "
            f"{RAINFALL_ACCUMULATION_TARGET_HOURS:.0f} ঘণ্টার মান পেতে দীর্ঘতর পূর্বাভাস ফাইল দিন।"
        )
        data_quality_warnings_en.append(
            f"Rainfall is reported as a {RAINFALL_ACCUMULATION_TARGET_HOURS:.0f}-hour accumulation, but "
            f"the uploaded NetCDF only spans {file_span:.0f} hours. The figure shown is therefore the "
            f"{used_hours:.0f}-hour accumulation and has not been extrapolated. Supply a longer forecast "
            "file for a full 72-hour total."
        )

    if model_normalized == "ccm":
        surge_series = pd.to_numeric(
            table_classification.get("Storm Surge (m)", pd.Series(dtype=float)), errors="coerce"
        )
        if surge_series.dropna().empty or float(surge_series.max(skipna=True) or 0.0) <= 0.0:
            data_quality_warnings.append(
                "CCM মডেল বাতাস ও জলোচ্ছ্বাস একসাথে ব্যবহার করে ঘরের ক্ষতি নির্ণয় করে, কিন্তু এই "
                "বিশ্লেষণে কোনো জলোচ্ছ্বাসের মান পাওয়া যায়নি (storm-surge ফাইল দেওয়া হয়নি বা "
                "সব মান শূন্য)। ফলে বাতাস যত বেশিই হোক, ঘরের ধরনভিত্তিক ক্ষতির শ্রেণী প্রকৃত "
                "অবস্থার চেয়ে কম দেখাতে পারে। (ক্ষতিগ্রস্ত জনসংখ্যা আলাদা সমীকরণ থেকে আসে, তাই "
                "সেটি এতে প্রভাবিত হয় না।) সঠিক ফলের জন্য storm-surge ফাইল দিন, অথবা শুধু "
                "বাতাসভিত্তিক ক্ষতির জন্য Safir-Simpson মডেল নির্বাচন করুন।"
            )
            data_quality_warnings_en.append(
                "The CCM model derives housing damage from wind and storm surge together, but this "
                "run has no surge values (no storm-surge file was supplied, or every value is zero). "
                "The per-house-type damage classes may therefore understate the event regardless of "
                "wind speed. (Affected population comes from a separate response curve and is not "
                "affected by this.) Supply a storm-surge file, or switch to the Safir-Simpson model "
                "for a wind-only damage assessment."
            )

    surge_time_metadata = read_netcdf_time_metadata(storm_bytes) if storm_bytes else None
    wind_time_metadata = cyclone_track.get("time_metadata", {})
    wind_start = wind_time_metadata.get("model_start_time_iso")
    surge_start = surge_time_metadata.get("start_time_iso") if surge_time_metadata else None
    if wind_start and surge_start:
        try:
            time_gap_hours = abs(
                (pd.Timestamp(wind_start) - pd.Timestamp(surge_start)).total_seconds()
            ) / 3600.0
        except Exception:
            time_gap_hours = 0.0
        if time_gap_hours > 1.0:
            data_quality_warnings.append(
                "ইনপুট সময়ের অসামঞ্জস্য: wind NetCDF শুরু "
                f"{wind_start}, কিন্তু storm-surge NetCDF শুরু {surge_start}। "
                "দুটি ফাইল একই model run-এর নয়; যৌথ wind–surge ক্ষয়ক্ষতি সিদ্ধান্তে "
                "ব্যবহারের আগে সঠিক একই-run storm-surge file দিন। Landfall time শুধু wind "
                "NetCDF-এর time coordinate থেকে গণনা করা হয়েছে।"
            )
            data_quality_warnings_en.append(
                f"Input time mismatch: the wind NetCDF starts at {wind_start}, but the "
                f"storm-surge NetCDF starts at {surge_start}. The two files are not from "
                "the same model run; supply a matching same-run storm-surge file before "
                "relying on combined wind-surge damage decisions. Landfall time was "
                "computed from the wind NetCDF time coordinate only."
            )

    track_map_path: Path | None = None
    if cyclone_track.get("available"):
        try:
            track_map_path = make_track_map_jpg(
                cyclone_track,
                gdf_upazila_map,
                output_path / "cyclone_track.jpg",
                cyclone_name,
            )
        except Exception as exc:  # noqa: BLE001 - map is non-fatal
            print(f"[track] JPEG map generation failed: {exc}", flush=True)
    print(f"[TIMING] analyze_cyclone_track: {time.time()-t0_track:.2f}s", flush=True)

    summary = {
        "input_type": input_type,
        "input_metadata": input_metadata,
        "total_unions": int(table_classification.shape[0]),
        "total_upazilas": len(per_upazila_contexts),
        "total_districts": len(per_district_contexts),
        "max_wind_speed_kmh": float(max_wind) if pd.notna(max_wind) else 0.0,
        "max_rainfall_mm": float(max_rainfall) if pd.notna(max_rainfall) else 0.0,
        "max_storm_surge_m": float(max_storm_surge) if pd.notna(max_storm_surge) else 0.0,
        "top_risk_unions": top_risk_names[:5],
        "top_risk_unions_top10": top_risk_names,
        "top_rain_unions_top10": top_rain_names,
        "top_risk_unions_display": ", ".join(top_risk_names),
        "top_rain_unions_display": ", ".join(top_rain_names),
        "max_wind_record": max_wind_record,
        "max_rain_record": max_rain_record,
        "max_storm_surge_record": max_storm_surge_record,
        "damage_model": model_normalized,
        "data_quality_warnings": data_quality_warnings,
        "data_quality_warnings_en": data_quality_warnings_en,
        "total_upazilas": len(per_upazila_contexts),
        "top_risk_upazilas": top_risk_names[:5],
        "top_risk_upazilas_top10": top_risk_names,
        "top_rain_upazilas_top10": top_rain_names,
        "top_risk_upazilas_display": ", ".join(top_risk_names),
        "top_rain_upazilas_display": ", ".join(top_rain_names),
    }

    risk_class_summary = {
        rc: {
            "max_wind": float(info["max_wind"]) if info.get("max_wind") and not pd.isna(info["max_wind"]) else None,
            "damages": info.get("damages", []),
            "evacuate": info.get("evacuate", []),
        }
        for rc, info in class_info.items()
    }
    print(f"[TIMING] Build summary statistics: {time.time()-t0:.2f}s", flush=True)

    t0 = time.time()
    _all_contexts = per_union_contexts_light + per_upazila_contexts + per_district_contexts
    manifest = {
        "input_path": str(input_path),
        "input_type": input_type,
        "input_metadata": input_metadata,
        "output_dir": str(output_path),
        "created_temp_output": created_temp_dir,
        "cyclone_name": cyclone_name,
        "guideline_markdown": guideline,
        "guideline_path": str(guideline_path),
        "risk_classification_excel": str(excel_results.get("classification_excel") or ""),
        "risk_classification_csv": str(classification_csv_path),
        "housing_damage_excel": str(excel_results.get("damage_excel") or ""),
        "housing_damage_csv": str(damage_csv_path),
        "rainfall_evacuation_excel": str(excel_results.get("rainfall_excel") or ""),
        "rainfall_evacuation_csv": str(rainfall_csv_path),
        "area_metrics_path": str(area_metrics_path),
        "gis_map_excel": str(excel_results.get("gis_map_excel") or ""),
        "risk_map_html": str(map_html) if map_html else "",
        "overall_damaged_types": overall_damaged_types,
        "risk_class_summary": risk_class_summary,
        "summary": summary,
        "polished": polished,
        "data_directory": str(data_path),
        "analysis_contexts": _all_contexts,
        "analysis_options": [
            {
                "geo_code": ctx.get("geo_code"),
                "name": ctx.get("name"),
                "admin_level": ctx.get("admin_level"),
                "union": ctx.get("union"),
                "upazila": ctx.get("upazila"),
                "district": ctx.get("district"),
                "wind_speed_kmh": ctx.get("wind_speed_kmh"),
                "risk": ctx.get("risk"),
            }
            for ctx in _all_contexts
            if ctx.get("name")
        ],
        "top_risk_unions_extended": top_risk_extended,
        "top_rain_unions_extended": top_rain_extended,
        "top_risk_upazilas_extended": top_risk_extended,
        "top_rain_upazilas_extended": top_rain_extended,
        "max_wind_record": max_wind_record,
        "max_rain_record": max_rain_record,
        "max_storm_surge_record": max_storm_surge_record,
        "wind_intensity_map_html": str(wind_intensity_map_path) if wind_intensity_map_path else None,
        "storm_surge_map_html": str(storm_surge_map_path) if storm_surge_map_path else None,
        "rainfall_risk_map_html": str(rainfall_risk_map_path) if rainfall_risk_map_path else None,
        "track_map_jpg": str(track_map_path) if track_map_path else None,
        "damage_model": model_normalized,
        "cyclone_track": cyclone_track,
        "wind_time_metadata": wind_time_metadata,
        "surge_time_metadata": surge_time_metadata,
        "data_quality_warnings": data_quality_warnings,
        "data_quality_warnings_en": data_quality_warnings_en,
    }
    print(f"[TIMING] Build manifest dict: {time.time()-t0:.2f}s", flush=True)
    
    print(f"[TIMING] === TOTAL PIPELINE TIME: {time.time()-t_start:.2f}s ===", flush=True)

    return manifest


def _write_manifest(path: str | Path, manifest: dict, pretty: bool) -> None:
    destination = Path(path).expanduser().resolve()
    destination.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2 if pretty else None),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Cyclone guideline toolkit CLI")
    parser.add_argument(
        "--input",
        required=True,
        help="Path to a NetCDF (.nc), CSV, or Excel (.xlsx) forecast file",
    )
    parser.add_argument(
        "--output",
        help="Directory where outputs will be written (defaults to temp directory)",
    )
    parser.add_argument(
        "--data-dir",
        help="Directory containing the household Excel and shapefile assets",
    )
    parser.add_argument(
        "--manifest",
        help="Optional path to write the JSON manifest returned by the processor",
    )
    parser.add_argument(
        "--no-polish",
        action="store_true",
        help="Skip LLM polishing of the Bengali guideline",
    )
    parser.add_argument(
        "--storm-surge",
        help="Optional NetCDF file containing storm surge heights (variable 'z')",
    )
    parser.add_argument(
        "--damage-model",
        choices=["safir", "ccm"],
        default="ccm",
        help="Housing damage model to use (default: ccm)",
    )
    parser.add_argument(
        "--cyclone-name",
        help="Optional cyclone name for metadata",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output (indentation)",
    )

    args = parser.parse_args()

    manifest = process_cyclone(
        nc_path=args.input,
        output_dir=args.output,
        data_dir=args.data_dir,
        polished=not args.no_polish,
        storm_surge_path=args.storm_surge,
        damage_model=args.damage_model,
        cyclone_name=args.cyclone_name,
    )

    if args.manifest:
        _write_manifest(args.manifest, manifest, args.pretty)

    print(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2 if args.pretty else None,
        )
    )


if __name__ == "__main__":
    main()
