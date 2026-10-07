"""
CCM computation engine — ported from the CCM 2.9 (with Rain) desktop tool's
`CCM_Update_Database.py`.

Original author: Md. Manjurul Husain Shourov (BUET). This is a faithful port
of that tool's `create_database()` logic, split so it can run for a single
new cyclone inside the portal's API instead of looping over a folder picked
in a desktop file dialog. All GUI (PyQt), plotting (matplotlib/contextily)
and interactive bits from the original have been dropped — none of them were
part of the actual calculation.

Inputs this engine needs for one new cyclone (normally produced by an
external storm-surge/wind/rain simulation run outside the portal, e.g. by
BUET, and uploaded here): a small set of raw grid files plus a cyclone track
shapefile. See `CycloneRawInputs` below for the exact file list.

Reference data (union boundaries, polder/structure/housing tables) is read
from the same `data/ccm/CycloneDataBase/` directory the portal already ships
and that `scripts/import_ccm.py` uses — nothing new to provision.

Output: a DataFrame with exactly the columns `scripts/import_ccm.py` expects
in a per-cyclone CSV (see its COLUMN_MAP), so the existing importer can load
the result into Postgres unchanged — this engine does not touch the database
itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

# ---------------------------------------------------------------------------
# Raw input contract for one new cyclone
# ---------------------------------------------------------------------------


@dataclass
class CycloneRawInputs:
    """Paths to the raw files for one new cyclone scenario.

    These are the files the original tool's "Ctrl+U -> select folder" import
    expected inside `<folder>/<cyclone_name>/`. `thrust_force_csv` is
    optional — if the simulation run already produced it, pass it directly;
    otherwise supply the three *_depth_averaged/_wind/_water_depth tf-grid
    files and it's computed here, matching the original tool.
    """

    water_depth_xyz: Path
    wind_speed_xyz: Path
    rain_csv: Path
    track_shp: Path  # plus matching .dbf/.shx/.prj beside it
    thrust_force_csv: Path | None = None
    water_depth_tf_xyz: Path | None = None
    wind_speed_tf_xyz: Path | None = None
    depth_avg_velocity_tf_xyz: Path | None = None


@dataclass
class CycloneMeta:
    """The row this cyclone gets in Cyclone_List.csv."""

    name: str
    type: str  # "Actual" or "Synthetic"
    date: str | None = None
    location: str | None = None
    angle: str | None = None
    remark: str = ""
    max_wind_speed_kmh: float | None = None


# Output column order/names `scripts/import_ccm.py` expects (COLUMN_MAP keys).
RESULT_COLUMNS = [
    "Division", "District", "Upazila", "Union", "Union_Geo",
    "Surge Height (m)", "Wind Speed (km/hr)", "Thrust Force",
    "72hr Cumulative Rainfall (mm)", "Polder Damage Condition",
    "Structure Damage Condition", "Agricultural Land Damage Condition",
    "Flooded Area (Km2)", "Percentage of Flooded Area",
    "House Damage in Million BDT", "Total Number of Affected House",
    "Total Number of Affected People", "Percentage of Affected People",
    "Hazard (%)", "Vulnerability (%)", "Risk (%)",
]


# ---------------------------------------------------------------------------
# Reference data (loaded once per run; cheap enough not to bother caching
# across requests for now — revisit if this becomes a hot path)
# ---------------------------------------------------------------------------


@dataclass
class CCMReferenceData:
    poly_without_river: gpd.GeoDataFrame
    poly_full: gpd.GeoDataFrame
    agri: gpd.GeoDataFrame
    polder_damage_matrix: pd.DataFrame
    polder_info: pd.DataFrame
    structure_damage_matrix: pd.DataFrame
    structure_damage_class: pd.DataFrame
    house_info: pd.DataFrame


def load_reference_data(data_dir: Path) -> CCMReferenceData:
    """Loads the union boundaries + lookup tables every run needs.

    `data_dir` is the portal's `data/ccm/CycloneDataBase` — same root
    `scripts/import_ccm.py` reads from. Note this uses the model's *own*
    `CCM_Unions_wgs84` / `CCM_Unions_without_River_wgs84` shapefiles for the
    spatial joins below (keyed by `Union_Geo`, matching the Base_info
    tables) — not `CCM_Unions_BBS21`, which is the display-only boundary
    swap used for the map. Mixing those up here would silently break every
    join in this module, since Base_info/StructureDamageData.xlsx etc. are
    keyed to the original CCM `Union_Geo` codes.
    """
    shp_dir = data_dir / "Shapefiles"
    base_dir = data_dir / "Base_info"

    poly_without_river = gpd.read_file(shp_dir / "CCM_Unions_without_River_wgs84.shp")
    poly_full = gpd.read_file(shp_dir / "CCM_Unions_wgs84.shp")
    agri = gpd.read_file(shp_dir / "Agri_Land_wgs84.shp")

    polder_damage_matrix = pd.read_excel(base_dir / "PolderInfo.xlsx", sheet_name="PolderDataMatrix")
    polder_info = pd.read_excel(base_dir / "PolderInfo.xlsx", sheet_name="PolderInfo_Union")

    structure_damage_matrix = pd.read_excel(
        base_dir / "StructureDamageData.xlsx", sheet_name="DamageMatrix", header=None
    )
    structure_damage_class = pd.read_excel(base_dir / "StructureDamageData.xlsx", sheet_name="Metadata")
    house_info = pd.read_excel(base_dir / "StructureDamageData.xlsx", sheet_name="Coastal_Housing_info")

    return CCMReferenceData(
        poly_without_river=poly_without_river,
        poly_full=poly_full,
        agri=agri,
        polder_damage_matrix=polder_damage_matrix,
        polder_info=polder_info,
        structure_damage_matrix=structure_damage_matrix,
        structure_damage_class=structure_damage_class,
        house_info=house_info,
    )


# ---------------------------------------------------------------------------
# Pure helper functions — unchanged logic from CCM_Update_Database.py,
# just type-annotated. Geopandas 0.10's `op=` kwarg is renamed `predicate=`
# in modern geopandas; `op` still works there via a deprecation shim, but
# use `predicate` if the installed version has dropped it.
# ---------------------------------------------------------------------------


def _sjoin_within(data: gpd.GeoDataFrame, polys: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    try:
        return gpd.sjoin(data, polys, predicate="within", how="left")
    except TypeError:  # geopandas < 0.10 only understands `op`
        return gpd.sjoin(data, polys, op="within", how="left")


def union_wise_reduce(data: gpd.GeoDataFrame, polys: gpd.GeoDataFrame, func: str, var_name: str):
    joined = _sjoin_within(data, polys)
    joined_clean = joined[~joined.Union_Geo.isna()]
    group_res = joined_clean.groupby("Union_Geo")["z"].agg(func)
    count_res = joined_clean.groupby("Union_Geo")["z"].count()
    group_res.name = var_name
    res = pd.merge(polys, group_res.to_frame(), on="Union_Geo", how="left")
    res.loc[res[var_name].isnull(), var_name] = 0
    return res, count_res


def union_wise_agri(data: gpd.GeoDataFrame, polys: gpd.GeoDataFrame, agri: gpd.GeoDataFrame, grid: pd.Series):
    joined_agri = _sjoin_within(data, agri)
    joined_clean_agri = joined_agri[~joined_agri.gridcode.isna()].drop("index_right", axis=1)

    joined = _sjoin_within(joined_clean_agri, polys)
    joined_clean = joined[~joined.Union_Geo.isna()]
    group_res = joined_clean.groupby("Union_Geo")["z"].count()

    aff_agri = round(group_res / grid * 100, 2)
    aff_agri.name = "Agricultural Land Damage Condition"
    res = pd.merge(polys, aff_agri.to_frame(), on="Union_Geo", how="left")
    res.loc[res["Agricultural Land Damage Condition"].isnull(), "Agricultural Land Damage Condition"] = 0
    return res


def union_wise_flood(data: gpd.GeoDataFrame, polys: gpd.GeoDataFrame, grid: pd.Series):
    joined_clean_agri = data[data["z"] > 0.3]

    joined = _sjoin_within(joined_clean_agri, polys)
    joined_clean = joined[~joined.Union_Geo.isna()]
    group_res = joined_clean.groupby("Union_Geo")["z"].count()

    aff_agri = round(group_res / grid * 100, 2)
    aff_agri.name = "Percentage of Flooded Area"
    aff_agri = aff_agri.to_frame()
    aff_agri["Flooded Area (Km2)"] = group_res * 0.3 * 0.3

    res = pd.merge(polys, aff_agri, on="Union_Geo", how="left")
    res.loc[res["Percentage of Flooded Area"].isnull(), "Percentage of Flooded Area"] = 0
    res.loc[res["Flooded Area (Km2)"].isnull(), "Flooded Area (Km2)"] = 0
    return res


def structure_damage_condition(df, damage_matrix, dm_class):
    if (df["Water Depth"] > 6) or (df["Wind Speed"] > 250):
        cls = 6
    else:
        cls = damage_matrix.loc[
            damage_matrix.loc[:, 0] >= df["Water Depth"], damage_matrix.loc[0, :] >= df["Wind Speed"]
        ].iloc[0, 0]
    return dm_class[dm_class.StructureDamageID == cls].StructureDamageClass.iloc[0]


def polder_damage_condition(df, pld_damage_matrix):
    if df["Thrust Force"] > 81.4:
        return "HP"
    if df.RegionID in pld_damage_matrix.columns:
        return pld_damage_matrix[pld_damage_matrix["Thrust Force"] > df["Thrust Force"]].loc[
            :, pld_damage_matrix.columns == df.RegionID
        ].iloc[-1, 0]
    return "No polder in the area"


def _pca_np_hz(dt, threshold: float = 1):
    if dt.shape[1] < 2:
        return 1

    data = dt - np.mean(dt, 0)
    c = np.corrcoef(data.T)
    e, v = np.linalg.eigh(np.abs(c))
    key = np.argsort(e)[::-1]
    e, v = e[key], v[:, key]
    com = np.abs(v) * np.sqrt(np.abs(e))

    e_thr = e[e >= threshold]
    com_thr = com[:, : len(e_thr)]

    wt = np.dot(com_thr, e_thr / e_thr.sum())
    return wt / sum(wt)


def hazard_calc(dt):
    dt = pd.DataFrame(dt)
    if any(dt.std(axis=0) == 0):
        rs = np.array([0.33, 0.33, 0.33])
    else:
        rs = _pca_np_hz(dt)

    hrz = np.dot(dt, rs)
    return (hrz / hrz.max()) * 100


def thrust_force_calc(data_wd, data_ws, data_vl):
    """Same storm-surge thrust-force derivation as the original tool.
    Needed only when the simulation run didn't already export
    'Thrush Force.csv' directly."""
    g = 9.81
    slope = 0.00001
    cd = 0.025
    cw = 0.002
    p = 1000
    n = 0.03
    t1 = 0.06

    s1 = -data_wd.z.diff() / 300
    s2 = -s1.diff() / 300
    s3 = -s2.diff() / 300

    uw1 = data_ws.z.diff() / 300
    uw3 = uw1.diff() / 300

    nitem = s3.dropna().shape[0]

    s1 = s1.iloc[-nitem:]
    s2 = s2.iloc[-nitem:]
    s3 = s3.iloc[-nitem:]
    uw1 = uw1.iloc[-nitem:]
    uw2 = data_ws.z.iloc[-nitem:]
    uw3 = uw3.iloc[-nitem:]
    u = data_vl.z.iloc[-nitem:]

    a = 300 * data_wd.z.iloc[-nitem:]
    pe = 300 + 2 * data_wd.z.iloc[-nitem:]
    rh = a / pe

    u1 = (rh ** (2 / 3) * slope ** (1 / 2)) / n

    y = g * s1 - g * slope + cd * rh ** (1 / 3) * slope / n**2 - (cw / rh) * uw2 * uw2
    y1 = g * s3 - 2 * cw * uw2 * uw3 - 2 * cw * uw1**2 / rh
    y2 = g * s2 - 2 * cw * uw2 * uw1 / rh

    u5 = (
        u1 - u1 * (g * s2 - 2 * cw * uw2 * uw1 / rh) * (t1**2) / 2
        + (g * s2 - 2 * cw * uw2 * uw1 / rh) * y * (t1**3) / 3
        - y * t1 + (cd / rh) * 2 * u1 * y * (t1**2) / 2 - cd / rh * y**2 * (t1**3) / 3
        + cw / rh * uw2**2 * t1
    )

    a1 = (
        -u1 * (g * s2 - 2 * cw * uw2 * uw1 / rh) * t1
        + (g * s2 - 2 * cw * uw2 * uw1 / rh) * y * (t1**2)
        - y + (cd / rh) * 2 * u1 * y * t1 - cd / rh * y**2 * (t1**2) + cw / rh * uw2**2
    )
    aterm = a1 * (u / u5)
    a2 = (
        -u1 * y1 * t1**2 / 2 + y2**2 * t1**3 / 3 + y * y1 * t1**3 / 3 - y2 * t1
        + 2 * cd * slope / (rh ** (1 / 3) * n) * y2 * t1**2 / 2
        - 2 * cd * y * y2 / rh * t1**3 / 3 - 2 * cw * uw2 * uw1 * t1 / rh
    )
    a3 = a2 * (u / u5)

    f1 = p * a * (aterm + u * a3)
    f1[f1.isna()] = 0
    f = f1.abs() / 300000

    f_res = data_wd[-nitem:].copy()
    f_res.z = f
    return f_res


def structure_damage_text(df):
    return "No" if df["Structure Damage Condition"] == "Pacca- No, Semi Pacca- No, Kacha- No" else "Yes"


def house_damage(df):
    cond = df["Structure Damage Condition"]
    if cond == "Pacca- No, Semi Pacca- No, Kacha- No":
        damage = 0
    elif cond in (
        "Pacca- No, Semi Pacca- No, Kacha- Partial",
        "Pacca- No, Semi Pacca- No, Kacha- Full",
    ):
        damage = df["Kacha_House"]
    elif cond == "Pacca- No, Semi Pacca- Partial, Kacha- Full":
        damage = df["Kacha_House"] + df["Semi-Paka_House"]
    else:  # the two "Full"/"Partial Pacca" tiers
        damage = df["Kacha_House"] + df["Semi-Paka_House"] + df["Paka_House"]
    return round(damage, 0)


def house_damage_cost(df):
    cond = df["Structure Damage Condition"]
    if cond == "Pacca- No, Semi Pacca- No, Kacha- No":
        damage_cost = 0
    elif cond == "Pacca- No, Semi Pacca- No, Kacha- Partial":
        damage_cost = df["Kacha_House"] * df["Damage_Repair_Partial_Kacha"]
    elif cond == "Pacca- No, Semi Pacca- No, Kacha- Full":
        damage_cost = df["Kacha_House"] * df["Damage_Repair_Full_Kacha"]
    elif cond == "Pacca- No, Semi Pacca- Partial, Kacha- Full":
        damage_cost = (
            df["Kacha_House"] * df["Damage_Repair_Full_Kacha"]
            + df["Semi-Paka_House"] * df["Damage_Repair_Partial_Semi-Paka"]
        )
    elif cond == "Pacca- Partial, Semi Pacca- Full, Kacha- Full":
        damage_cost = (
            df["Kacha_House"] * df["Damage_Repair_Full_Kacha"]
            + df["Semi-Paka_House"] * df["Damage_Repair_Full_Semi-Paka"]
            + df["Paka_House"] * df["Damage_Repair_Partial_Paka"]
        )
    else:  # "Pacca- Full, Semi Pacca- Full, Kacha- Full"
        damage_cost = (
            df["Kacha_House"] * df["Damage_Repair_Full_Kacha"]
            + df["Semi-Paka_House"] * df["Damage_Repair_Full_Semi-Paka"]
            + df["Paka_House"] * df["Damage_Repair_Full_Paka"]
        )

    return round(df["Households_No"] * damage_cost, 0)


def agri_class(df):
    return "No" if df["Agricultural Land Damage Condition"] == 0 else "Yes"


# District-wise affected-people regression curves, exactly as calibrated in
# the original tool (one polynomial/exponential fit per coastal district).
_AFFECTED_PEOPLE_CURVES = {
    "Bagerhat": lambda x: 0.0176 * x**2 - 1.1289 * x + 20.239,
    "Barguna": lambda x: -4.737002 + 0.577665 * x - 0.01124983 * x**2 + 0.00008988237 * x**3,
    "Barisal": lambda x: 0.0067 * x**2 - 0.5229 * x + 10.896,
    "Bhola": lambda x: 11.89156 - 0.7341249 * x + 0.01451025 * x**2 - 0.00007200953 * x**3,
    "Chandpur": lambda x: 0.2375 * np.exp(0.0704 * x),
    "Chittagong": lambda x: 0.0046 * x**2 - 0.5444 * x + 17.707,
    "Cox's Bazar": lambda x: -0.0015 * x**2 + 0.411 * x - 3.0263,
    "Feni": lambda x: 0.0094 * x**2 - 0.4303 * x + 5.935,
    "Gopalganj": lambda x: 10**-5 * x**3.6145,
    "Jessore": lambda x: 133.2208 - 14.26508 * x + 0.4987643 * x**2 - 0.005299058 * x**3,
    "Jhalokati": lambda x: 0.007 * x**2 - 0.241 * x + 3.2083,
    "Khulna": lambda x: 0.0029 * x**2 + 0.0684 * x + 0.3357,
    "Lakshmipur": lambda x: 0.0039 * x**2 - 0.1673 * x + 1.8,
    "Narail": lambda x: -0.0435 * x**2 + 3.2717 * x - 10.323,
    "Noakhali": lambda x: -0.0003 * x**2 + 0.0791 * x + 0.0863,
    "Patuakhali": lambda x: 6.347361 - 0.4238161 * x + 0.01093494 * x**2 - 0.00004070469 * x**3,
    "Pirojpur": lambda x: 1.142 * np.exp(0.0318 * x),
    "Satkhira": lambda x: 1.0256 * np.exp(0.0387 * x),
    "Shariatpur": lambda x: 0.0056 * x**2 + 0.252 * x - 4.2952,
}


def affected_people(df):
    x = df["Wind Speed (km/hr)_y"]
    curve = _AFFECTED_PEOPLE_CURVES.get(df.District)
    return curve(x) if curve else np.nan


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_ccm_for_cyclone(
    ref: CCMReferenceData,
    inputs: CycloneRawInputs,
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Computes the per-union CCM result for one new cyclone.

    Returns `(result_df, track_gdf)`:
    - `result_df` has exactly `RESULT_COLUMNS`, matching what
      `scripts/import_ccm.py` reads from a `Cyclone_Info/<name>.csv`.
    - `track_gdf` is the cyclone track, to save as
      `Cyclone_Track/<name>.shp` the same way the original tool did.

    Raises on malformed/missing input the same way the original would
    (unhandled pandas/geopandas errors) — the caller is expected to catch
    and turn these into a useful HTTP error, since there's no good generic
    way to validate arbitrary simulation output up front.
    """
    poly_without_river = ref.poly_without_river
    poly_full = ref.poly_full

    column_name = {
        "DIVNAME": "Division",
        "DISTNAME": "District",
        "Water Depth": "Surge Height (m)",
        "Wind Speed": "Wind Speed (km/hr)",
    }
    polder_classes = {"HP": "Yes", "MP": "Yes", "LP": "No"}

    # --- Thrust force -----------------------------------------------------
    if inputs.thrust_force_csv is not None:
        data_tf = pd.read_csv(inputs.thrust_force_csv)
    else:
        if not (inputs.water_depth_tf_xyz and inputs.wind_speed_tf_xyz and inputs.depth_avg_velocity_tf_xyz):
            raise ValueError(
                "Need either thrust_force_csv, or all three of "
                "water_depth_tf_xyz/wind_speed_tf_xyz/depth_avg_velocity_tf_xyz."
            )
        data_wd = pd.read_csv(inputs.water_depth_tf_xyz, header=None, names=["x", "y", "z"], sep=r"\s+", skiprows=3)
        idx = (data_wd.z >= 0) & (data_wd.z <= 12)
        data_wd = data_wd[idx]

        data_ws = pd.read_csv(
            inputs.wind_speed_tf_xyz, header=None, names=["x", "y", "p", "q"], sep=r"\s+", skiprows=4
        )
        data_ws["z"] = np.sqrt(data_ws.p**2 + data_ws.q**2)
        data_ws = data_ws.loc[:, ["x", "y", "z"]][idx]

        data_vl = pd.read_csv(
            inputs.depth_avg_velocity_tf_xyz, header=None, names=["x", "y", "p", "q"], sep=r"\s+", skiprows=4
        )
        data_vl["z"] = np.sqrt(data_vl.p**2 + data_vl.q**2)
        data_vl = data_vl.loc[:, ["x", "y", "z"]][idx]

        data_tf = thrust_force_calc(data_wd, data_ws, data_vl)

    # --- Main grids ---------------------------------------------------------
    data_wd = pd.read_csv(inputs.water_depth_xyz, header=None, names=["x", "y", "z"], sep=r"\s+", skiprows=3)
    data_wd = data_wd[data_wd.loc[:, "z"] > 0]
    data_wd["Point"] = [Point(xyz) for xyz in zip(data_wd.iloc[:, 0], data_wd.iloc[:, 1])]
    data_wd = gpd.GeoDataFrame(data_wd, geometry=data_wd.Point, crs=poly_full.crs)

    data_ws = pd.read_csv(inputs.wind_speed_xyz, header=None, names=["x", "y", "p", "q"], sep=r"\s+", skiprows=4)
    data_ws["z"] = np.sqrt(data_ws.p**2 + data_ws.q**2) * 3.6
    data_ws = data_ws.loc[:, ["x", "y", "z"]]
    data_ws["Point"] = [Point(xyz) for xyz in zip(data_ws.iloc[:, 0], data_ws.iloc[:, 1])]
    data_ws = gpd.GeoDataFrame(data_ws, geometry=data_ws.Point, crs=poly_full.crs)

    data_tf = data_tf[data_tf.loc[:, "z"] > 0]
    data_tf["Point"] = [Point(xyz) for xyz in zip(data_tf.iloc[:, 0], data_tf.iloc[:, 1])]
    data_tf = gpd.GeoDataFrame(data_tf, geometry=data_tf.Point, crs=poly_full.crs)

    data_rain = pd.read_csv(inputs.rain_csv)
    data_rain = data_rain.groupby(["Longitude", "Latitude"], as_index=False).sum()
    data_rain["Point"] = [Point(xyz) for xyz in zip(data_rain["Longitude"], data_rain["Latitude"])]
    data_rain = gpd.GeoDataFrame(data_rain, geometry=data_rain.Point, crs=poly_full.crs)

    # --- Union-wise aggregation ---------------------------------------------
    res_wd, _count = union_wise_reduce(data_wd, poly_without_river, "mean", "Water Depth")
    res_ws, total_grid_no = union_wise_reduce(data_ws, poly_full, "max", "Wind Speed")
    res_tf, _c = union_wise_reduce(data_tf, poly_full, "max", "Thrust Force")

    res_rain = gpd.sjoin_nearest(poly_full, data_rain, how="left")
    res_rain["Rain"] = res_rain["Rain"].round(0)
    res_agri = union_wise_agri(data_wd, poly_full, ref.agri, total_grid_no)
    res_flood_area = union_wise_flood(data_wd, poly_full, total_grid_no)

    f_res = (
        res_wd.merge(res_ws.loc[:, ["Union_Geo", "Wind Speed"]], on="Union_Geo")
        .merge(res_tf.loc[:, ["Union_Geo", "Thrust Force"]], on="Union_Geo")
        .merge(res_rain.loc[:, ["Union_Geo", "Rain"]], on="Union_Geo")
        .merge(res_agri.loc[:, ["Union_Geo", "Agricultural Land Damage Condition"]], on="Union_Geo")
        .merge(
            res_flood_area.loc[:, ["Union_Geo", "Flooded Area (Km2)", "Percentage of Flooded Area"]],
            on="Union_Geo",
        )
    )

    temp = pd.merge(f_res, ref.polder_info.loc[:, ["Union_Geo", "RegionID"]], on=["Union_Geo"])
    f_res["Polder Damage Condition"] = temp.apply(polder_damage_condition, args=(ref.polder_damage_matrix,), axis=1)
    f_res["Structure Damage Condition"] = f_res.apply(
        structure_damage_condition, args=(ref.structure_damage_matrix, ref.structure_damage_class), axis=1
    )
    f_res["Agricultural Land Damage Condition"] = f_res.apply(agri_class, axis=1)

    # --- Hazard --------------------------------------------------------------
    f_res.loc[
        (f_res["Water Depth"] == 0) & (f_res["Polder Damage Condition"] != "No polder in the area"),
        "Polder Damage Condition",
    ] = "LP"
    f_res["Hazard (%)"] = hazard_calc(f_res.loc[:, ["Water Depth", "Wind Speed", "Thrust Force"]])

    f_res["Polder Damage Condition"] = f_res["Polder Damage Condition"].replace(polder_classes)
    f_res["Water Depth"] = f_res["Water Depth"].round(1)
    if any(f_res["Water Depth"] > 6):
        f_res.loc[f_res["Water Depth"] > 6, "Water Depth"] = 6
    f_res["Wind Speed"] = f_res["Wind Speed"].astype(int)
    f_res = f_res.rename(column_name, axis=1)

    f_res = pd.merge(
        f_res,
        ref.house_info.loc[
            :,
            [
                "Union_Geo", "Households_No", "Paka_House", "Semi-Paka_House", "Kacha_House", "Population",
                "Asset_Paka_House", "Asset_Semi-Paka_House", "Asset_Kacha_House",
                "Damage_Repair_Partial_Paka", "Damage_Repair_Full_Paka",
                "Damage_Repair_Partial_Semi-Paka", "Damage_Repair_Full_Semi-Paka",
                "Damage_Repair_Partial_Kacha", "Damage_Repair_Full_Kacha",
            ],
        ],
        on=["Union_Geo"],
    )

    f_res["Exposed Households"] = f_res.apply(house_damage, axis=1)
    f_res["Exposed Population"] = f_res["Exposed Households"] * f_res["Population"] / 100
    f_res[["Exposed Households", "Exposed Population"]] = f_res[["Exposed Households", "Exposed Population"]].round()
    f_res["Asset Value"] = f_res["Households_No"] * (
        f_res["Paka_House"] * f_res["Asset_Paka_House"]
        + f_res["Semi-Paka_House"] * f_res["Asset_Semi-Paka_House"]
        + f_res["Kacha_House"] * f_res["Asset_Kacha_House"]
    )
    f_res["House Damage in Million BDT"] = f_res.apply(house_damage_cost, axis=1)

    f_res["Vulnerability (%)"] = f_res["House Damage in Million BDT"] / f_res["Asset Value"]
    f_res["Risk (%)"] = (f_res["Hazard (%)"] * f_res["Vulnerability (%)"]) ** 0.5

    f_res["House Damage in Million BDT"] = round(f_res["House Damage in Million BDT"] / 1_000_000, 0)
    f_res["Hazard (%)"] = f_res["Hazard (%)"].round(0)
    f_res["Vulnerability (%)"] = (
        (f_res["Vulnerability (%)"] - f_res["Vulnerability (%)"].min())
        / (f_res["Vulnerability (%)"].max() - f_res["Vulnerability (%)"].min())
        * 100
    ).round(0)
    f_res["Risk (%)"] = (
        (f_res["Risk (%)"] - f_res["Risk (%)"].min()) / (f_res["Risk (%)"].max() - f_res["Risk (%)"].min()) * 100
    ).round(0)

    f_res["Structure Damage Condition"] = f_res.apply(structure_damage_text, axis=1)

    dist_ws = f_res.groupby("District").mean(numeric_only=True).loc[:, ["Wind Speed (km/hr)"]]
    f_res = f_res.join(dist_ws, on="District", rsuffix="_y")
    f_res = f_res.merge(ref.house_info.loc[:, ["Union_Geo", "m", "Dis_Population"]], on="Union_Geo")
    f_res["Dist_aff"] = f_res.apply(affected_people, axis=1)

    f_res["Total Number of Affected People"] = abs(round(f_res["Dist_aff"] * f_res["m"] * f_res["Dis_Population"] / 100, 0))
    f_res["Total Number of Affected House"] = round(f_res["Total Number of Affected People"] / 4, 0)
    f_res.loc[f_res["Structure Damage Condition"] == "No", "Total Number of Affected People"] = 0
    f_res.loc[f_res["Structure Damage Condition"] == "No", "Total Number of Affected House"] = 0

    f_res["Percentage of Affected People"] = round(f_res["Total Number of Affected House"] / f_res["Population"] * 100, 0)
    f_res.loc[f_res["Percentage of Affected People"] == 0, "Percentage of Affected People"] = 1
    f_res.loc[f_res["Structure Damage Condition"] == "No", "Percentage of Affected People"] = 0

    f_res.loc[f_res["Surge Height (m)"] == 0, "Agricultural Land Damage Condition"] = "No"
    f_res = f_res.rename(columns={"Rain": "72hr Cumulative Rainfall (mm)"})

    result_df = f_res.loc[:, RESULT_COLUMNS].sort_values("Union_Geo").reset_index(drop=True)

    track_gdf = gpd.read_file(inputs.track_shp)

    return result_df, track_gdf
