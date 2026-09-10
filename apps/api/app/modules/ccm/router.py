"""CCM routes — Module 5, Cyclone Classifier Model.

These endpoints serve results the CCM produced. They do not run the model.
Adding a new cyclone's results is an import (see scripts/import_ccm.py and, in
future, the portal's own upload endpoint), after which it appears here exactly
like the cyclones shipped with the model package.
"""
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.core.deps import DbSession
from app.modules.ccm import metrics as metric_registry
from app.modules.ccm import service
from app.modules.ccm.schemas import (
    AdminLevel,
    CycloneDetail,
    CycloneSummary,
    LocationOption,
    MapResponse,
    MetricInfo,
    Operator,
    ResultPage,
)

router = APIRouter(prefix="/ccm", tags=["CCM"])


@router.get("/metrics", response_model=list[MetricInfo])
async def list_metrics() -> list[dict]:
    """The metrics available for mapping, triggering and display."""
    return [m.as_dict() for m in metric_registry.METRICS]


@router.get("/cyclones", response_model=list[CycloneSummary])
async def list_cyclones(db: DbSession) -> list[dict]:
    """Every cyclone whose CCM results are loaded — shipped or uploaded."""
    return await service.list_cyclones(db)


@router.get("/cyclones/{code}", response_model=CycloneDetail)
async def get_cyclone(code: str, db: DbSession) -> dict:
    """One cyclone, with headline totals across all unions."""
    return await service.get_cyclone(db, code)


@router.get("/cyclones/{code}/locations", response_model=list[LocationOption])
async def get_locations(
    code: str,
    db: DbSession,
    level: Annotated[str, Query(pattern="^(division|district|upazila)$")] = "division",
    parent: str | None = None,
) -> list[dict]:
    """Options for the cascading location picker."""
    return await service.locations(db, code, level, parent)


@router.get("/cyclones/{code}/results", response_model=ResultPage)
async def get_results(
    code: str,
    db: DbSession,
    level: AdminLevel = "union",
    division: str | None = None,
    district: str | None = None,
    upazila: str | None = None,
    metric: str | None = None,
    operator: Operator | None = None,
    threshold: float | None = None,
    page: int = 1,
    size: int = 50,
) -> dict:
    """The results table, aggregated to the requested administrative level."""
    return await service.results(
        db,
        code=code,
        level=level,
        division=division,
        district=district,
        upazila=upazila,
        metric=metric,
        operator=operator,
        threshold=threshold,
        page=page,
        size=size,
    )


@router.get("/cyclones/{code}/map", response_model=MapResponse)
async def get_map(
    code: str,
    db: DbSession,
    metric: str | None = None,
    division: str | None = None,
    district: str | None = None,
    upazila: str | None = None,
    operator: Operator | None = None,
    threshold: float | None = None,
    simplify: float = 0.001,
) -> dict:
    """Union polygons with the selected metric attached, as GeoJSON."""
    return await service.map_features(
        db,
        code=code,
        metric=metric,
        division=division,
        district=district,
        upazila=upazila,
        operator=operator,
        threshold=threshold,
        simplify=simplify,
    )


@router.get("/cyclones/{code}/results.csv")
async def export_results_csv(
    code: str,
    db: DbSession,
    level: AdminLevel = "union",
    division: str | None = None,
    district: str | None = None,
    upazila: str | None = None,
    metric: str | None = None,
    operator: Operator | None = None,
    threshold: float | None = None,
) -> StreamingResponse:
    """The current table as CSV — the web equivalent of the tool's 'Save Table'."""
    import csv
    import io

    payload = await service.results(
        db,
        code=code,
        level=level,
        division=division,
        district=district,
        upazila=upazila,
        metric=metric,
        operator=operator,
        threshold=threshold,
        page=1,
        size=2000,
    )
    rows = payload["items"]

    buffer = io.StringIO()
    if rows:
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    buffer.seek(0)
    filename = f"CCM_{code}_{level}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
