"""Preparedness Guidance routes — Module 3.

Upload a cyclone forecast, the portal runs the impact + guidance pipeline
asynchronously (Celery worker -> model service), and these endpoints expose the
run history, each run's results, and its downloadable artifacts.
"""
import io
import json
import re
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from app.core import storage
from app.core.config import settings
from app.core.deps import DbSession
from app.core.exceptions import NotFoundError, UpstreamServiceError, ValidationError
from app.core.tasks import enqueue_preparedness
from app.modules.preparedness import service
from app.modules.preparedness.schemas import (
    AreaMapBody,
    DocxBody,
    GuidelineBody,
    RunDetail,
    RunSummary,
    SaveGuidelineBody,
)

router = APIRouter(prefix="/preparedness", tags=["Preparedness"])

_ALLOWED = {".nc", ".csv", ".xlsx", ".xls"}
_SVC = settings.PREPAREDNESS_SERVICE_URL
_SVC_TIMEOUT = settings.PREPAREDNESS_REQUEST_TIMEOUT
#: shared `prep-runs` volume, mounted read-only on the API for on-demand maps.
_RUNS_ROOT = Path("/runs")


def _slug(value: str) -> str:
    return re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", (value or "").lower()))[:48]


def _inputs_prefix(run_id: int) -> str:
    return f"preparedness/{run_id}/inputs"


def _artifacts_prefix(run_id: int) -> str:
    return f"preparedness/{run_id}/artifacts"


def _check_ext(upload: UploadFile, label: str) -> None:
    if Path(upload.filename or "").suffix.lower() not in _ALLOWED:
        raise ValidationError(f"{label} file must be one of {sorted(_ALLOWED)}.")


@router.post("/runs", response_model=RunDetail, status_code=201)
async def create_run(
    db: DbSession,
    cyclone_name: Annotated[str, Form()],
    wind: Annotated[UploadFile, File()],
    rainfall: Annotated[UploadFile | None, File()] = None,
    storm_surge: Annotated[UploadFile | None, File()] = None,
    damage_model: Annotated[str, Form()] = "ccm",
    polish: Annotated[bool, Form()] = True,
) -> RunDetail:
    """Queue a new preparedness run from an uploaded wind forecast."""
    if damage_model not in ("ccm", "safir"):
        raise ValidationError("damage_model must be 'ccm' or 'safir'.")
    _check_ext(wind, "Wind-speed")
    for label, f in (("Rainfall", rainfall), ("Storm-surge", storm_surge)):
        if f is not None:
            _check_ext(f, label)

    # Insert first so the row id can namespace the object keys.
    run = await service.create_run(
        db,
        cyclone_name=cyclone_name.strip() or "cyclone",
        damage_model=damage_model,
        polished=polish,
        input_files={},
    )

    input_files: dict = {}
    for role, upload in (("wind", wind), ("rainfall", rainfall), ("storm_surge", storm_surge)):
        if upload is None:
            continue
        filename = Path(upload.filename or f"{role}.nc").name
        key = f"{_inputs_prefix(run.id)}/{role}_{filename}"
        storage.put_fileobj(key, upload.file, upload.content_type)
        input_files[role] = {"filename": filename, "key": key}

    run.input_files = input_files
    await db.commit()
    await db.refresh(run)

    enqueue_preparedness(run.id)
    return RunDetail.model_validate(run)


@router.get("/runs", response_model=list[RunSummary])
async def list_runs(db: DbSession) -> list[RunSummary]:
    runs = await service.list_runs(db)
    return [RunSummary.model_validate(r) for r in runs]


@router.get("/runs/{run_id}", response_model=RunDetail)
async def get_run(run_id: int, db: DbSession) -> RunDetail:
    run = await service.get_run(db, run_id)
    return RunDetail.model_validate(run)


@router.get("/runs/{run_id}/artifacts/{name}")
async def get_artifact(run_id: int, name: str, db: DbSession) -> StreamingResponse:
    """Stream one artifact (map HTML, Excel, CSV, …) from object storage."""
    run = await service.get_run(db, run_id)
    artifacts = run.artifacts or []
    match = next((a for a in artifacts if a.get("name") == name), None)
    if match is None:
        raise NotFoundError(f"No artifact '{name}' on run {run_id}.")

    body = storage.open_stream(match["key"])
    headers = {"Content-Disposition": f'inline; filename="{name}"'}
    return StreamingResponse(
        body.iter_chunks(),
        media_type=match.get("content_type") or "application/octet-stream",
        headers=headers,
    )


# ------------------------------------------------------------ interactive (Phase 2)


@router.get("/runs/{run_id}/contexts")
async def get_contexts(run_id: int, db: DbSession) -> StreamingResponse:
    """Per-area analysis contexts + options for the area explorer (from storage)."""
    await service.get_run(db, run_id)  # 404 if the run does not exist
    key = f"preparedness/{run_id}/contexts.json"
    if not storage.object_exists(key):
        raise NotFoundError(f"No contexts for run {run_id} (run may still be processing).")
    body = storage.open_stream(key)
    return StreamingResponse(body.iter_chunks(), media_type="application/json")


@router.post("/runs/{run_id}/guideline")
async def generate_guideline(run_id: int, payload: GuidelineBody, db: DbSession):
    """Generate the structured, per-area guideline for the selected area (LLM)."""
    run = await service.get_run(db, run_id)
    summary = run.summary or {}
    cyclone_track = summary.get("cyclone_track") or {}
    lead_time = (cyclone_track.get("forecast_state") or {}).get("lead_time_hours")
    rainfall_window = (summary.get("input_metadata") or {}).get("rainfall_accumulation_hours")
    warnings = summary.get("data_quality_warnings_en") if payload.lang == "en" else summary.get("data_quality_warnings")

    req = {
        "cyclone_name": run.cyclone_name,
        "context": payload.context,
        "cyclone_track": cyclone_track,
        "lang": payload.lang,
        "lead_time_hours": lead_time,
        "data_quality_warnings": warnings,
        "rainfall_window_hours": rainfall_window,
    }
    try:
        resp = httpx.post(f"{_SVC}/guideline", json=req, timeout=_SVC_TIMEOUT)
    except httpx.HTTPError as exc:
        raise UpstreamServiceError("Guideline service unreachable.", details={"error": str(exc)}) from exc
    if resp.status_code != 200:
        detail = resp.text
        try:
            detail = resp.json().get("detail", detail)
        except Exception:  # noqa: BLE001
            pass
        return JSONResponse(status_code=resp.status_code, content={"error": {"message": detail}})
    return resp.json()


@router.post("/runs/{run_id}/area-map")
async def area_map(run_id: int, payload: AreaMapBody, db: DbSession) -> FileResponse:
    """Generate (or reuse) an area-focused metric map PNG and stream it back."""
    await service.get_run(db, run_id)
    out_dir = _RUNS_ROOT / str(run_id) / "out"
    metrics_path = out_dir / "area_metrics.json"
    area_key = _slug(payload.geo_code) or _slug(
        "-".join(p for p in (payload.union, payload.upazila, payload.district) if p)
    ) or "area"
    filename = f"areamap_{payload.level}_{area_key}_{payload.metric}.png"
    output = out_dir / filename
    req = {
        "level": payload.level,
        "metric": payload.metric,
        "output": str(output),
        "metrics_path": str(metrics_path),
        "district": payload.district,
        "upazila": payload.upazila,
        "union": payload.union,
        "geo_code": payload.geo_code,
        "lang": payload.lang,
    }
    try:
        resp = httpx.post(f"{_SVC}/area-map", json=req, timeout=_SVC_TIMEOUT)
    except httpx.HTTPError as exc:
        raise UpstreamServiceError("Area-map service unreachable.", details={"error": str(exc)}) from exc
    if resp.status_code != 200:
        detail = resp.text
        try:
            detail = resp.json().get("detail", detail)
        except Exception:  # noqa: BLE001
            pass
        raise UpstreamServiceError("Area map generation failed.", details={"detail": detail})
    if not output.exists():
        raise NotFoundError("Area map was not produced.")
    return FileResponse(str(output), media_type="image/png", filename=filename)


@router.post("/runs/{run_id}/guideline/docx")
async def guideline_docx(run_id: int, payload: DocxBody, db: DbSession) -> Response:
    """Render a GuidelineDocument to a .docx (proxied from the model service)."""
    await service.get_run(db, run_id)
    try:
        resp = httpx.post(
            f"{_SVC}/guideline/docx",
            json={"document": payload.document, "track_map_b64": payload.track_map_b64},
            timeout=_SVC_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise UpstreamServiceError("Docx service unreachable.", details={"error": str(exc)}) from exc
    if resp.status_code != 200:
        raise UpstreamServiceError("Docx generation failed.", details={"detail": resp.text})
    name = _slug(payload.document.get("cycloneName") or "guideline") or "guideline"
    return Response(
        content=resp.content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{name}_ibf_guideline.docx"'},
    )


@router.post("/runs/{run_id}/guideline/save")
async def save_guideline(run_id: int, payload: SaveGuidelineBody, db: DbSession) -> dict:
    """Persist an (edited) guideline document as a JSON artifact."""
    await service.get_run(db, run_id)
    key = f"preparedness/{run_id}/guidelines/{_slug(payload.area_name) or 'guideline'}.json"
    data = io.BytesIO(json.dumps(payload.document, ensure_ascii=False).encode("utf-8"))
    storage.put_fileobj(key, data, "application/json")
    return {"ok": True, "key": key}
