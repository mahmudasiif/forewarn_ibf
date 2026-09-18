"""DFRM routes — Module 7, Flood Risk.

A stateless proxy in front of the DFRM model service. The portal picks an area
and a water level; these endpoints return either a graded flood layer (GeoJSON,
rendered as a Leaflet choropleth) or the per-area flood warning table.
"""
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.core.deps import DbSession
from app.modules.dfrm import service
from app.modules.dfrm.schemas import Level, MapBody, RunSummary, WarningBody, WLKind

router = APIRouter(prefix="/dfrm", tags=["DFRM"])


@router.get("/areas")
async def get_areas() -> dict:
    """The District → Upazilla → Union → Village picker + stations/limbs/layers."""
    return await service.areas()


@router.post("/map")
async def post_map(body: MapBody, db: DbSession) -> dict:
    """A graded flood layer for the selected area, as a GeoJSON choropleth."""
    request = body.model_dump()
    result = await service.map_layer(request)
    await service.record_run(db, kind="map", request=request, result=result)
    return result


@router.post("/warning")
async def post_warning(body: WarningBody, db: DbSession) -> dict:
    """The per-area flood warning table for the selected area + water level."""
    request = body.model_dump()
    result = await service.warning(request)
    await service.record_run(db, kind="warning", request=request, result=result)
    return result


@router.get("/runs", response_model=list[RunSummary])
async def list_runs(db: DbSession, limit: Annotated[int, Query(ge=1, le=200)] = 50) -> list[RunSummary]:
    """Recent DFRM queries (the portal's audit trail), newest first."""
    return [RunSummary.model_validate(r) for r in await service.list_runs(db, limit)]


@router.get("/runs/count")
async def runs_count(db: DbSession) -> dict:
    """Total number of recorded DFRM queries."""
    return {"count": await service.count_runs(db)}


@router.get("/warning.csv")
async def export_warning_csv(
    area_id: str,
    water_level: float,
    level: Level = "Union",
    wl_kind: WLKind = "WL",
    limb: str = "Flood Increasing",
    date: Annotated[str | None, Query()] = None,
) -> StreamingResponse:
    """The warning table as CSV — the web equivalent of the tool's 'Save'."""
    result = await service.warning(
        {
            "level": level,
            "area_id": area_id,
            "water_level": water_level,
            "wl_kind": wl_kind,
            "limb": limb,
            "date": date,
        }
    )
    body = service.warning_csv(result)
    filename = f"DFRM_warning_{level}_{area_id}.csv"
    return StreamingResponse(
        iter([body]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
