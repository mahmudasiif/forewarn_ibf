"""Persisting CCM results that the model produced for a portal-started run.

`scripts/import_ccm.py` does the same job for the CSVs shipped with the CCM
package: it reads a file from disk. This module takes rows the model service
just computed, in memory, and writes them to the same two tables with the
same semantics (replace a cyclone's rows wholesale; merge the handful of
multi-cell unions by maximum).

The two paths are kept separate on purpose. The importer is the only way the
shipped package is loaded and is run by hand against production data; folding
it into this would mean every change here could break that. The column map
below is the contract they share — if the CCM result header ever changes,
both need updating together.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

#: CCM result column -> database column. Mirrors COLUMN_MAP in
#: scripts/import_ccm.py; the model service returns rows keyed by the left side.
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

TEXT_COLUMNS = {
    "division",
    "district",
    "upazila",
    "union_name",
    "polder_damage",
    "structure_damage",
    "agri_land_damage",
}

NUMERIC_COLUMNS = [c for c in COLUMN_MAP.values() if c not in TEXT_COLUMNS and c != "union_geo"]


def pretty_name(code: str) -> str:
    """'Sidr_rain_Actual' -> 'Sidr';  'Cyclone_1991_actual' -> 'Cyclone 1991'."""
    name = re.sub(r"_(rain_)?actual$", "", code, flags=re.IGNORECASE)
    return name.replace("_", " ").strip().title()


def _to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


async def persist_run_results(
    db: AsyncSession,
    *,
    code: str,
    rows: list[dict[str, Any]],
    meta: dict[str, Any],
    track: dict | None = None,
) -> tuple[int, int]:
    """Writes one run's results. Returns `(cyclone_id, rows_written)`.

    Re-running the same code replaces that cyclone's rows rather than
    duplicating them, so a corrected re-run is simply run again.
    """
    event_date = meta.get("event_date")
    if isinstance(event_date, str):
        event_date = _parse_date(event_date)

    cyclone_id = (
        await db.execute(
            text(
                """
                INSERT INTO ccm.cyclones
                    (code, name, event_date, landfall_location, max_wind_speed,
                     remark, cyclone_type, source, model_version, track_geojson)
                VALUES
                    (:code, :name, :event_date, :landfall_location, :max_wind_speed,
                     :remark, :cyclone_type, :source, :model_version,
                     CAST(:track AS jsonb))
                ON CONFLICT (code) DO UPDATE SET
                    name              = EXCLUDED.name,
                    event_date        = EXCLUDED.event_date,
                    landfall_location = EXCLUDED.landfall_location,
                    max_wind_speed    = EXCLUDED.max_wind_speed,
                    remark            = EXCLUDED.remark,
                    cyclone_type      = EXCLUDED.cyclone_type,
                    source            = EXCLUDED.source,
                    track_geojson     = COALESCE(EXCLUDED.track_geojson,
                                                 ccm.cyclones.track_geojson),
                    imported_at       = NOW()
                RETURNING id
                """
            ),
            {
                "code": code,
                "name": meta.get("name") or pretty_name(code),
                "event_date": event_date,
                "landfall_location": meta.get("landfall_location"),
                "max_wind_speed": meta.get("max_wind_speed"),
                "remark": meta.get("remark"),
                "cyclone_type": meta.get("cyclone_type", "realtime"),
                "source": "upload",
                "model_version": meta.get("model_version", "v2.9.3"),
                "track": json.dumps(track) if track else None,
            },
        )
    ).scalar_one()

    await db.execute(text("DELETE FROM ccm.results WHERE cyclone_id = :cid"), {"cid": cyclone_id})

    columns = ["cyclone_id", "union_geo", "division", "district", "upazila", "union_name"]
    columns += [c for c in COLUMN_MAP.values() if c not in columns]
    placeholders = ", ".join(f":{c}" for c in columns)
    insert_sql = text(
        f"INSERT INTO ccm.results ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT (cyclone_id, union_geo) DO NOTHING"
    )

    # The Sundarbans forest ranges span more than one rainfall cell, so the
    # model emits several rows for one union that differ only in rainfall.
    # Merge by maximum: for a warning system the higher value over the area is
    # the safe one to carry forward. (Same rule as the package importer.)
    merged: dict[int, dict] = {}
    for row in rows:
        raw_id = row.get("Union_Geo")
        if raw_id in (None, ""):
            continue
        try:
            union_geo = int(float(raw_id))
        except (TypeError, ValueError):
            continue

        values: dict[str, Any] = {"cyclone_id": cyclone_id, "union_geo": union_geo}
        for source_col, target_col in COLUMN_MAP.items():
            if target_col == "union_geo":
                continue
            raw = row.get(source_col)
            if target_col in TEXT_COLUMNS:
                values[target_col] = "" if raw is None else str(raw).strip()
            else:
                values[target_col] = _to_float(raw)

        existing = merged.get(union_geo)
        if existing is None:
            merged[union_geo] = values
            continue

        for column in NUMERIC_COLUMNS:
            new, old = values.get(column), existing.get(column)
            if new is None:
                continue
            existing[column] = new if old is None else max(old, new)

    batch = list(merged.values())
    if batch:
        await db.execute(insert_sql, batch)
    await db.commit()

    return cyclone_id, len(batch)


def _parse_date(value: str) -> date | None:
    """Accepts the package's 'DD MM YYYY' and the browser's ISO 'YYYY-MM-DD'."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        pass
    parts = value.split()
    if len(parts) == 3:
        try:
            day, month, year = (int(p) for p in parts)
            return date(year, month, day)
        except ValueError:
            return None
    return None
