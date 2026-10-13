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
    ThresholdMode,
    TrackResponse,
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
    threshold_mode: ThresholdMode = "value",
    lead_time_hours: Annotated[int | None, Query(ge=0, le=168)] = None,
    page: int = 1,
    size: int = 50,
) -> dict:
    """The results table, aggregated to the requested administrative level.

    `threshold_mode=return_period` reads `threshold` as a number of years and
    keeps the unions where this cyclone is worse than their own T-year event,
    rather than comparing the trigger metric to a flat number.

    `lead_time_hours` adds the four NEAP columns — the lead time itself and the
    impact number for wind, storm surge and rainfall.
    """
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
        threshold_mode=threshold_mode,
        lead_time_hours=lead_time_hours,
        page=page,
        size=size,
    )


@router.get("/cyclones/{code}/map", response_model=MapResponse)
async def get_map(
    code: str,
    db: DbSession,
    metric: str | None = None,
    level: AdminLevel = "union",
    division: str | None = None,
    district: str | None = None,
    upazila: str | None = None,
    operator: Operator | None = None,
    threshold: float | None = None,
    threshold_mode: ThresholdMode = "value",
    simplify: float = 0.001,
) -> dict:
    """Polygons for the chosen level, with the metric attached, as GeoJSON.

    At union level these are the 1,585 union polygons. Above it they are the
    upazilas, districts or divisions dissolved from those unions and carrying
    the aggregated figure, so the map shows the same areas the table lists.
    """
    return await service.map_features(
        db,
        code=code,
        metric=metric,
        level=level,
        division=division,
        district=district,
        upazila=upazila,
        operator=operator,
        threshold=threshold,
        threshold_mode=threshold_mode,
        simplify=simplify,
    )


@router.get("/cyclones/{code}/track", response_model=TrackResponse)
async def get_track(code: str, db: DbSession) -> dict:
    """The cyclone's track line, for drawing over the map."""
    return await service.get_track(db, code)


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


#: Spreadsheet-friendly headers for the download. Anything not listed keeps
#: its raw column name — a new metric still exports, it just exports unlabelled
#: until someone names it here.
EXPORT_HEADERS: dict[str, str] = {
    "union_geo": "Union_Geo",
    "division": "Division",
    "district": "District",
    "upazila": "Upazila",
    "union_name": "Union",
    "surge_height_m": "Surge Height (m)",
    "wind_speed_kmh": "Wind Speed (km/hr)",
    "thrust_force": "Thrust Force",
    "rainfall_72h_mm": "72hr Cumulative Rainfall (mm)",
    "polder_damage": "Polder Damage Condition",
    "structure_damage": "Structure Damage Condition",
    "agri_land_damage": "Agricultural Land Damage Condition",
    "flooded_area_km2": "Flooded Area (Km2)",
    "flooded_area_pct": "Percentage of Flooded Area",
    "house_damage_million_bdt": "House Damage in Million BDT",
    "affected_houses": "Total Number of Affected House",
    "affected_people": "Total Number of Affected People",
    "affected_people_pct": "Percentage of Affected People",
    "hazard_pct": "Hazard (%)",
    "vulnerability_pct": "Vulnerability (%)",
    "risk_pct": "Risk (%)",
    "lead_time_hours": "Lead Time in Hours",
    "neap_wind": "NEAP Risk Impact Number for Wind",
    "neap_surge": "NEAP Risk Impact Number for Surge",
    "neap_rain": "NEAP Risk Impact Number for Rain",
}


async def _export_payload(
    db: DbSession,
    code: str,
    level: AdminLevel,
    division: str | None,
    district: str | None,
    upazila: str | None,
    metric: str | None,
    operator: Operator | None,
    threshold: float | None,
    threshold_mode: ThresholdMode,
    lead_time_hours: int | None,
) -> tuple[list[str], list[str], list[dict]]:
    """Run the current filters unpaged and return (keys, headers, rows)."""
    payload = await service.export_rows(
        db,
        code=code,
        level=level,
        division=division,
        district=district,
        upazila=upazila,
        metric=metric,
        operator=operator,
        threshold=threshold,
        threshold_mode=threshold_mode,
        lead_time_hours=lead_time_hours,
    )
    rows = payload["items"]
    keys = list(rows[0].keys()) if rows else []
    return keys, [EXPORT_HEADERS.get(k, k) for k in keys], rows


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
    threshold_mode: ThresholdMode = "value",
    lead_time_hours: Annotated[int | None, Query(ge=0, le=168)] = None,
) -> StreamingResponse:
    """The whole filtered table as CSV — the tool's 'Save Table', unpaged."""
    import csv
    import io

    keys, headers, rows = await _export_payload(
        db, code, level, division, district, upazila,
        metric, operator, threshold, threshold_mode, lead_time_hours,
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    if keys:
        writer.writerow(headers)
        writer.writerows([row.get(k) for k in keys] for row in rows)

    # Excel reads a bare UTF-8 CSV as Windows-1252 and mangles any non-ASCII
    # place name; the BOM is what tells it otherwise.
    return StreamingResponse(
        iter(["\ufeff" + buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="CCM_{code}_{level}.csv"'
        },
    )


@router.get("/cyclones/{code}/results.xlsx")
async def export_results_xlsx(
    code: str,
    db: DbSession,
    level: AdminLevel = "union",
    division: str | None = None,
    district: str | None = None,
    upazila: str | None = None,
    metric: str | None = None,
    operator: Operator | None = None,
    threshold: float | None = None,
    threshold_mode: ThresholdMode = "value",
    lead_time_hours: Annotated[int | None, Query(ge=0, le=168)] = None,
) -> StreamingResponse:
    """The same table as a real .xlsx, which is what the desktop tool saved."""
    import io

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    keys, headers, rows = await _export_payload(
        db, code, level, division, district, upazila,
        metric, operator, threshold, threshold_mode, lead_time_hours,
    )

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "CCM Results"

    if keys:
        sheet.append(headers)
        header_fill = PatternFill("solid", fgColor="053244")  # navy-900
        for index in range(1, len(headers) + 1):
            cell = sheet.cell(row=1, column=index)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = header_fill
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            # Wide enough for the header, capped so one long label does not
            # push the numeric columns off the screen.
            sheet.column_dimensions[get_column_letter(index)].width = min(
                max(12, len(headers[index - 1]) + 2), 34
            )
        sheet.row_dimensions[1].height = 30
        sheet.freeze_panes = "A2"

        for row in rows:
            sheet.append([row.get(key) for key in keys])

        sheet.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(rows) + 1}"

    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": f'attachment; filename="CCM_{code}_{level}.xlsx"'
        },
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
