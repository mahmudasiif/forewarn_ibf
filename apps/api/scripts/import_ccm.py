"""
Load the CCM v2.9.3 cyclone database into PostgreSQL/PostGIS.

The CCM package ships its results as plain data: one CSV per cyclone giving the
model's output for every union, plus a shapefile of the union boundaries the two
join on (`Union_Geo`). This script reads both and loads them into the `ccm`
schema, after which the portal serves the results itself and the desktop tool is
not needed to view them.

Usage (inside the api container):

    python -m scripts.import_ccm --data-dir /data/ccm/CycloneDataBase
    python -m scripts.import_ccm --data-dir /data/ccm/CycloneDataBase --reset

Adding a single new cyclone later (e.g. a result file produced by a real-time
run and uploaded through the portal):

    python -m scripts.import_ccm --data-dir /data/ccm/CycloneDataBase \
        --only REMAL_Actual --source upload
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

import shapefile  # pyshp
from sqlalchemy import text

from app.core.db import SessionLocal

# CSV column -> database column. The CCM result header is fixed across all
# cyclones in v2.9.3; if a future version changes it, update this map.
COLUMN_MAP: dict[str, str] = {
    "Division": "division",
    "District": "district",
    "Upazila": "upazila",
    "Union": "union_name",
    "Union_Geo": "union_geo",
    "Surge Height (m)": "surge_height_m",
    "Wind Speed (km/hr)": "wind_speed_kmh",
    "Thrust Force": "thrust_force",
    "72hr Cumulative Rainfall (mm)": "rainfall_72h_mm",
    "Polder Damage Condition": "polder_damage",
    "Structure Damage Condition": "structure_damage",
    "Agricultural Land Damage Condition": "agri_land_damage",
    "Flooded Area (Km2)": "flooded_area_km2",
    "Percentage of Flooded Area": "flooded_area_pct",
    "House Damage in Million BDT": "house_damage_million_bdt",
    "Total Number of Affected House": "affected_houses",
    "Total Number of Affected People": "affected_people",
    "Percentage of Affected People": "affected_people_pct",
    "Hazard (%)": "hazard_pct",
    "Vulnerability (%)": "vulnerability_pct",
    "Risk (%)": "risk_pct",
}

# Condition columns carry one of: 'Yes', 'No', 'No polder in the area'.
TEXT_COLUMNS = {
    "division",
    "district",
    "upazila",
    "union_name",
    "polder_damage",
    "structure_damage",
    "agri_land_damage",
}

NUMERIC_COLUMNS = [
    c for c in COLUMN_MAP.values() if c not in TEXT_COLUMNS and c != "union_geo"
]


def pretty_name(code: str) -> str:
    """'Sidr_rain_Actual' -> 'Sidr';  'Cyclone_1991_actual' -> 'Cyclone 1991'."""
    name = re.sub(r"_(rain_)?actual$", "", code, flags=re.IGNORECASE)
    return name.replace("_", " ").strip().title()


def parse_date(value: str) -> date | None:
    """The package writes dates as 'DD MM YYYY'."""
    parts = (value or "").split()
    if len(parts) != 3:
        return None
    try:
        day, month, year = (int(p) for p in parts)
        return date(year, month, day)
    except ValueError:
        return None


def to_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_cyclone_list(data_dir: Path) -> dict[str, dict]:
    """Cyclone_List.csv — the package's own index of cyclones."""
    path = data_dir / "Cyclone_List.csv"
    if not path.exists():
        print(f"  ! {path.name} not found — cyclone metadata will be minimal")
        return {}

    index: dict[str, dict] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            code = (row.get("Name") or "").strip()
            if not code:
                continue
            index[code] = {
                "name": pretty_name(code),
                "event_date": parse_date((row.get("Date") or "").strip()),
                "landfall_location": (row.get("Location") or "").strip() or None,
                "max_wind_speed": to_float((row.get("Max Wind Speed") or "").strip()),
                "remark": (row.get("Remark") or "").strip() or None,
                "cyclone_type": "actual" if (row.get("Type") or "").strip().lower() == "actual" else "realtime",
            }
    return index


async def import_unions(session, data_dir: Path) -> int:
    """Load the union boundaries. Idempotent — re-running refreshes geometry."""
    base = data_dir / "Shapefiles" / "CCM_Unions_wgs84"
    if not base.with_suffix(".shp").exists():
        raise SystemExit(f"Union shapefile not found at {base}.shp")

    reader = shapefile.Reader(str(base))
    print(f"  reading {len(reader)} union polygons …")

    inserted = 0
    for record in reader.iterShapeRecords():
        attrs = record.record.as_dict()
        union_geo = attrs.get("Union_Geo")
        if union_geo in (None, ""):
            continue

        geometry = record.shape.__geo_interface__
        # Normalise Polygon -> MultiPolygon so the column type is uniform.
        if geometry["type"] == "Polygon":
            geometry = {"type": "MultiPolygon", "coordinates": [geometry["coordinates"]]}

        await session.execute(
            text(
                """
                INSERT INTO ccm.unions
                    (union_geo, division, district, upazila, union_name, geom)
                VALUES
                    (:union_geo, :division, :district, :upazila, :union_name,
                     ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326)))
                ON CONFLICT (union_geo) DO UPDATE SET
                    division   = EXCLUDED.division,
                    district   = EXCLUDED.district,
                    upazila    = EXCLUDED.upazila,
                    union_name = EXCLUDED.union_name,
                    geom       = EXCLUDED.geom
                """
            ),
            {
                "union_geo": int(union_geo),
                "division": (attrs.get("Division") or "").strip(),
                "district": (attrs.get("District") or "").strip(),
                "upazila": (attrs.get("Upazila") or "").strip(),
                "union_name": (attrs.get("Union") or "").strip(),
                "geom": json.dumps(geometry),
            },
        )
        inserted += 1

    await session.commit()
    return inserted


async def import_cyclone(session, csv_path: Path, meta: dict, source: str) -> int:
    """Load one cyclone's result table. Re-running replaces its rows."""
    code = csv_path.stem

    cyclone_id = (
        await session.execute(
            text(
                """
                INSERT INTO ccm.cyclones
                    (code, name, event_date, landfall_location, max_wind_speed,
                     remark, cyclone_type, source, model_version)
                VALUES
                    (:code, :name, :event_date, :landfall_location, :max_wind_speed,
                     :remark, :cyclone_type, :source, :model_version)
                ON CONFLICT (code) DO UPDATE SET
                    name              = EXCLUDED.name,
                    event_date        = EXCLUDED.event_date,
                    landfall_location = EXCLUDED.landfall_location,
                    max_wind_speed    = EXCLUDED.max_wind_speed,
                    remark            = EXCLUDED.remark,
                    imported_at       = NOW()
                RETURNING id
                """
            ),
            {
                "code": code,
                "name": meta.get("name") or pretty_name(code),
                "event_date": meta.get("event_date"),
                "landfall_location": meta.get("landfall_location"),
                "max_wind_speed": meta.get("max_wind_speed"),
                "remark": meta.get("remark"),
                "cyclone_type": meta.get("cyclone_type", "actual"),
                "source": source,
                "model_version": "v2.9.3",
            },
        )
    ).scalar_one()

    await session.execute(
        text("DELETE FROM ccm.results WHERE cyclone_id = :cid"), {"cid": cyclone_id}
    )

    columns = ["cyclone_id", "union_geo", "division", "district", "upazila", "union_name"]
    columns += [c for c in COLUMN_MAP.values() if c not in columns]
    placeholders = ", ".join(f":{c}" for c in columns)
    insert_sql = text(
        f"INSERT INTO ccm.results ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT (cyclone_id, union_geo) DO NOTHING"
    )

    # A few large unions — the Sundarbans forest ranges — span more than one
    # rainfall cell, so the model writes several rows for one union_geo that
    # differ only in rainfall. Merge them, taking the maximum of each numeric
    # field: for a warning system the higher value over the area is the safe
    # one to carry forward. Every other field is identical across the rows.
    merged: dict[int, dict] = {}
    duplicates = 0

    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            clean = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
            raw_id = clean.get("Union_Geo")
            if not raw_id:
                continue
            try:
                union_geo = int(float(raw_id))
            except ValueError:
                continue

            values: dict = {"cyclone_id": cyclone_id, "union_geo": union_geo}
            for source_col, target_col in COLUMN_MAP.items():
                if target_col == "union_geo":
                    continue
                raw = clean.get(source_col, "")
                # Blank numeric cells stay NULL — e.g. the forest ranges have no
                # resident population, so vulnerability and risk are undefined
                # there, which is meaningfully different from zero.
                values[target_col] = raw if target_col in TEXT_COLUMNS else to_float(raw)

            existing = merged.get(union_geo)
            if existing is None:
                merged[union_geo] = values
                continue

            duplicates += 1
            for column in NUMERIC_COLUMNS:
                new, old = values.get(column), existing.get(column)
                if new is None:
                    continue
                existing[column] = new if old is None else max(old, new)

    batch = list(merged.values())
    if batch:
        await session.execute(insert_sql, batch)
    await session.commit()

    if duplicates:
        print(f"      ({duplicates} multi-cell rows merged by maximum)")
    return len(batch)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Import the CCM cyclone database.")
    parser.add_argument(
        "--data-dir",
        default="/data/ccm/CycloneDataBase",
        help="Path to the CycloneDataBase folder from the CCM package.",
    )
    parser.add_argument("--only", help="Import a single cyclone by its file stem.")
    parser.add_argument(
        "--source", default="package", choices=["package", "upload"],
        help="How these results reached the portal.",
    )
    parser.add_argument("--skip-unions", action="store_true", help="Skip boundary import.")
    parser.add_argument(
        "--reset", action="store_true", help="Delete all CCM data before importing."
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        raise SystemExit(
            f"Data directory not found: {data_dir}\n"
            "Copy the CycloneDataBase folder from the CCM package into data/ccm/ "
            "in the project root, then run this again."
        )

    async with SessionLocal() as session:
        if args.reset:
            print("Resetting ccm schema …")
            await session.execute(text("TRUNCATE ccm.results, ccm.cyclones RESTART IDENTITY CASCADE"))
            await session.execute(text("TRUNCATE ccm.unions CASCADE"))
            await session.commit()

        if not args.skip_unions:
            print("Importing union boundaries …")
            count = await import_unions(session, data_dir)
            print(f"  {count} unions loaded.\n")

        index = read_cyclone_list(data_dir)
        info_dir = data_dir / "Cyclone_Info"
        if not info_dir.exists():
            raise SystemExit(f"Cyclone_Info folder not found at {info_dir}")

        files = sorted(info_dir.glob("*.csv"))
        if args.only:
            files = [f for f in files if f.stem.lower() == args.only.lower()]
            if not files:
                raise SystemExit(f"No result file matching '{args.only}' in {info_dir}")

        print(f"Importing {len(files)} cyclone result table(s) …")
        total = 0
        for path in files:
            meta = index.get(path.stem, {})
            rows = await import_cyclone(session, path, meta, args.source)
            total += rows
            label = meta.get("name") or pretty_name(path.stem)
            when = meta.get("event_date")
            print(f"  {label:<16} {when or '':<12} {rows:>5} unions")

        print(f"\nDone. {total} result rows across {len(files)} cyclone(s).")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(1)
