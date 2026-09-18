"""DFRM service layer — proxy to the model micro-service, CSV export, and the
portal's own audit trail of queries.

The DFRM model is stateless; the portal records each map/warning query in the
`dfrm.runs` table so operators get a run history (the model service itself still
persists nothing).
"""
import csv
import io

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.dfrm_client import dfrm_client
from app.modules.dfrm.models import DfrmRun

# Column order for the warning CSV, by admin level (mirrors the desktop tool).
_BASE_COLS = ["Risk Level", "Water Depth", "Flood Duration", "Water Speed", "Damage"]
_LEVEL_COLS = {
    "District": ["Division", "District"],
    "Upazilla": ["Division", "District", "Upazilla"],
    "Union": ["Division", "District", "Upazilla", "Union"],
    "Village": ["Division", "District", "Upazilla", "Union", "Village"],
}


async def areas() -> dict:
    return await dfrm_client.areas()


async def map_layer(payload: dict) -> dict:
    return await dfrm_client.map_layer(payload)


async def warning(payload: dict) -> dict:
    return await dfrm_client.warning(payload)


# --------------------------------------------------------------- run history


async def record_run(db: AsyncSession, *, kind: str, request: dict, result: dict) -> DfrmRun | None:
    """Persist one map/warning query as an audit-trail row.

    Best-effort: the audit trail must never break a working map/warning, so a
    write failure is rolled back and swallowed rather than surfaced.
    """
    if kind == "map":
        summary = {
            "day": result.get("day"),
            "feature_count": result.get("feature_count"),
            "metric_min": result.get("metric_min"),
            "metric_max": result.get("metric_max"),
            "metric_unit": result.get("metric_unit"),
        }
        layer = result.get("layer") or request.get("layer") or "Inundation"
    else:
        selected = result.get("selected") or {}
        summary = {
            "day": result.get("day"),
            "risk_level": selected.get("Risk Level"),
            "water_depth": selected.get("Water Depth"),
            "row_count": len(result.get("rows") or []),
        }
        layer = "Warning"

    run = DfrmRun(
        kind=kind,
        level=result.get("level") or request.get("level"),
        area_id=result.get("area_id") or request.get("area_id"),
        area_name=result.get("area_name") or request.get("area_id"),
        layer=layer,
        water_level=result.get("water_level", request.get("water_level")),
        wl_kind=request.get("wl_kind", "WL"),
        limb=result.get("limb") or request.get("limb"),
        date=result.get("date") or request.get("date"),
        river=result.get("river", ""),
        station=result.get("station", ""),
        return_period=result.get("return_period"),
        summary=summary,
    )
    try:
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run
    except Exception:  # noqa: BLE001 — audit trail must not break the query
        await db.rollback()
        return None


async def list_runs(db: AsyncSession, limit: int = 50) -> list[DfrmRun]:
    rows = await db.execute(select(DfrmRun).order_by(DfrmRun.created_at.desc()).limit(limit))
    return list(rows.scalars().all())


async def count_runs(db: AsyncSession) -> int:
    from sqlalchemy import func

    total = await db.execute(select(func.count()).select_from(DfrmRun))
    return int(total.scalar_one())


def warning_csv(result: dict) -> str:
    """Serialise a warning result to CSV: an info block, then the table.

    Matches the desktop tool's 'Save' output — station / water level / date /
    condition / return period header rows, followed by the per-area table.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    writer.writerow(["Station", result.get("station")])
    writer.writerow(["FFWC Water Level (m)", result.get("water_level")])
    writer.writerow(["Date of Warning", result.get("date") or ""])
    writer.writerow(["Flood Condition", result.get("limb")])
    # Original tool only records the return period for a >= 2-year event; below
    # that the GEV fit isn't meaningful, so it's omitted (Return_label hidden).
    rp = result.get("return_period")
    if rp is not None and rp >= 2:
        writer.writerow(["Return Period", rp])
    writer.writerow([])

    level = result.get("level", "Union")
    columns = _LEVEL_COLS.get(level, _LEVEL_COLS["Union"]) + _BASE_COLS
    dict_writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    dict_writer.writeheader()
    for row in result.get("rows", []):
        dict_writer.writerow(row)

    return buffer.getvalue()
