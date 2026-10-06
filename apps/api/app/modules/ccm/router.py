"""CCM routes — Module 5, Cyclone Classifier Model.

These endpoints serve results the CCM produced. They do not run the model.
Adding a new cyclone's results is an import (see scripts/import_ccm.py and, in
future, the portal's own upload endpoint), after which it appears here exactly
like the cyclones shipped with the model package.
"""
import re
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.core.deps import DbSession
from app.modules.ccm import metrics as metric_registry
from app.modules.ccm import runs as run_service
from app.modules.ccm import service
from app.modules.ccm.schemas import (
    AdminLevel,
    BoundaryResponse,
    CycloneDetail,
    CycloneSummary,
    LocationOption,
    MapResponse,
    MetricInfo,
    Operator,
    ResultPage,
    RunAccepted,
    RunSummary,
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


@router.get("/cyclones/{code}/boundaries", response_model=BoundaryResponse)
async def get_boundaries(
    code: str,
    db: DbSession,
    level: Annotated[str, Query(pattern="^(district|division)$")] = "district",
    division: str | None = None,
    district: str | None = None,
    upazila: str | None = None,
    simplify: float = 0.002,
) -> dict:
    """District or division outlines for the map, dissolved from the unions."""
    return await service.boundaries(
        db,
        code=code,
        level=level,
        division=division,
        district=district,
        upazila=upazila,
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


# --------------------------------------------------------------------------
# Running the model
#
# Everything above serves results the model already produced. These endpoints
# produce new ones: an operator uploads the simulation output for a cyclone
# (generated upstream by the storm-surge modelling team, not here) and the
# CCM computes hazard, vulnerability and risk for all 1,585 coastal unions.
# --------------------------------------------------------------------------

#: Letters, digits, underscore and hyphen. The code becomes a URL segment and
#: a database key, and must match across re-runs, so keep it strict.
CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,120}$")


@router.post("/runs", response_model=RunAccepted, status_code=202)
async def start_run(
    db: DbSession,
    background: BackgroundTasks,
    cyclone_code: Annotated[str, Form()],
    water_depth_xyz: Annotated[UploadFile, File()],
    wind_speed_xyz: Annotated[UploadFile, File()],
    rain_csv: Annotated[UploadFile, File()],
    track_shp: Annotated[UploadFile, File()],
    track_shx: Annotated[UploadFile, File()],
    track_dbf: Annotated[UploadFile, File()],
    track_prj: Annotated[UploadFile | None, File()] = None,
    track_cpg: Annotated[UploadFile | None, File()] = None,
    thrust_force_csv: Annotated[UploadFile | None, File()] = None,
    water_depth_tf_xyz: Annotated[UploadFile | None, File()] = None,
    wind_speed_tf_xyz: Annotated[UploadFile | None, File()] = None,
    depth_avg_velocity_tf_xyz: Annotated[UploadFile | None, File()] = None,
    name: Annotated[str | None, Form()] = None,
    event_date: Annotated[str | None, Form()] = None,
    landfall_location: Annotated[str | None, Form()] = None,
    max_wind_speed: Annotated[float | None, Form()] = None,
    remark: Annotated[str | None, Form()] = None,
    cyclone_type: Annotated[str, Form()] = "realtime",
) -> dict:
    """Starts a model run. Returns immediately; poll `/ccm/runs/{id}`.

    Re-using a `cyclone_code` replaces that cyclone's existing results once
    the run succeeds — which is how a corrected re-run is done.
    """
    if not CODE_PATTERN.match(cyclone_code):
        raise HTTPException(
            status_code=422,
            detail=(
                "cyclone_code must be 3-120 characters, letters, digits, "
                "underscore or hyphen only."
            ),
        )

    uploads: dict[str, UploadFile | None] = {
        "water_depth_xyz": water_depth_xyz,
        "wind_speed_xyz": wind_speed_xyz,
        "rain_csv": rain_csv,
        "track_shp": track_shp,
        "track_shx": track_shx,
        "track_dbf": track_dbf,
        "track_prj": track_prj,
        "track_cpg": track_cpg,
        "thrust_force_csv": thrust_force_csv,
        "water_depth_tf_xyz": water_depth_tf_xyz,
        "wind_speed_tf_xyz": wind_speed_tf_xyz,
        "depth_avg_velocity_tf_xyz": depth_avg_velocity_tf_xyz,
    }

    has_tf_grids = all(
        uploads[f] is not None and uploads[f].filename
        for f in ("water_depth_tf_xyz", "wind_speed_tf_xyz", "depth_avg_velocity_tf_xyz")
    )
    has_tf_csv = thrust_force_csv is not None and thrust_force_csv.filename
    if not (has_tf_csv or has_tf_grids):
        raise HTTPException(
            status_code=422,
            detail=(
                "Thrust force is required: upload the pre-computed "
                "'Thrush Force.csv', or all three of the thrust-force grids "
                "(water depth, wind speed, depth-averaged velocity)."
            ),
        )

    # Read the uploads here rather than in the background task: the request's
    # temporary files are closed as soon as it returns.
    files: list[tuple[str, tuple[str, bytes, str]]] = []
    manifest: dict[str, dict] = {}
    for field, upload in uploads.items():
        if upload is None or not upload.filename:
            continue
        content = await upload.read()
        files.append((field, (upload.filename, content, upload.content_type or "application/octet-stream")))
        manifest[field] = {"filename": upload.filename, "bytes": len(content)}

    meta = {
        "name": name or None,
        "event_date": event_date or None,
        "landfall_location": landfall_location or None,
        "max_wind_speed": max_wind_speed,
        "remark": remark or None,
        "cyclone_type": cyclone_type,
    }

    run_id = await run_service.create_run(db, code=cyclone_code, meta=meta, manifest=manifest)
    background.add_task(
        run_service.execute_run, run_id, code=cyclone_code, meta=meta, files=files
    )
    return {"id": run_id, "cyclone_code": cyclone_code, "status": "queued"}


@router.get("/runs", response_model=list[RunSummary])
async def list_runs(db: DbSession, limit: int = Query(20, ge=1, le=100)) -> list[dict]:
    """Recent model runs, newest first."""
    return await run_service.list_runs(db, limit)


@router.get("/runs/{run_id}", response_model=RunSummary)
async def get_run(run_id: int, db: DbSession) -> dict:
    """One run's status — what the browser polls while a run is in flight."""
    run = await run_service.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="No such run")
    return run
