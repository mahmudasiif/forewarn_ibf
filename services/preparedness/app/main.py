"""Cyclone Preparedness Guidance — model micro-service.

Portal model-service contract:

    GET  /health     liveness + GIS-cache readiness
    GET  /info       name, version, readiness, input/output schema
    POST /predict    run the impact pipeline for one forecast (synchronous)

Unlike services/_template this service is deliberately synchronous with no
in-memory job store: the portal's Celery worker is the async layer and calls
`/predict` from inside a background task. The pipeline warm-loads ~200 MB of BBS
GIS boundaries once at startup (`load_all_gis_data`) and serves each request from
an in-memory copy (`copy_gis_bundle`), so a request never re-reads the shapefiles
and concurrent requests never see each other's mutations.
"""
from __future__ import annotations

import base64
import binascii
import json
import time
import traceback
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse

from app.model import pipeline
from app.schemas import (
    AreaMapRequest,
    GuidelineDocxRequest,
    GuidelineRequest,
    InfoResponse,
    PredictRequest,
    PredictResponse,
)
from app.settings import settings

app = FastAPI(title=f"FOREWARN model — {settings.MODEL_NAME}", version=settings.MODEL_VERSION)

_GIS_CACHE: dict | None = None
_LOAD_ERROR: str | None = None


@app.on_event("startup")
def _load_gis_data_once() -> None:
    global _GIS_CACHE, _LOAD_ERROR
    t0 = time.time()
    print("[preparedness] loading GIS/housing data into memory...", flush=True)
    try:
        _GIS_CACHE = pipeline.load_all_gis_data()
        print(
            f"[preparedness] GIS cached in {time.time() - t0:.1f}s "
            f"({len(_GIS_CACHE['gdf_union_full'])} unions, "
            f"{len(_GIS_CACHE['gdf_upazila'])} upazilas)",
            flush=True,
        )
    except Exception as exc:  # noqa: BLE001 - surface via /health, do not crash boot
        _LOAD_ERROR = f"{exc}\n{traceback.format_exc()}"
        print(f"[preparedness] FAILED to preload GIS data: {exc}", flush=True)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok" if _GIS_CACHE is not None else "loading",
        "model": settings.MODEL_NAME,
        "version": settings.MODEL_VERSION,
        "gis_loaded": _GIS_CACHE is not None,
        "llm_available": settings.llm_available,
        "error": _LOAD_ERROR,
    }


@app.get("/info", response_model=InfoResponse)
def info() -> InfoResponse:
    return InfoResponse(
        name=settings.MODEL_NAME,
        version=settings.MODEL_VERSION,
        ready=_GIS_CACHE is not None,
        llm_available=settings.llm_available,
        input_schema=PredictRequest.model_json_schema(),
        output_schema=PredictResponse.model_json_schema(),
    )


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    """Run the pipeline. Paths in the body live on the volume shared with the
    worker; the worker uploads the resulting artifacts to object storage."""
    if _GIS_CACHE is None:
        detail = _LOAD_ERROR or "GIS data is still loading; retry shortly."
        return JSONResponse(status_code=503, content={"status": "error", "detail": detail})

    # Only attempt LLM polish when a key is actually configured — otherwise the
    # vendored pipeline would warn on every run. No key => base guideline.
    polished = req.polished and settings.llm_available
    try:
        bundle = pipeline.copy_gis_bundle(_GIS_CACHE)
        manifest = pipeline.process_cyclone(
            nc_path=req.input,
            output_dir=req.output,
            data_dir=None,
            polished=polished,
            rainfall_path=req.rainfall,
            storm_surge_path=req.storm_surge,
            damage_model=req.damage_model,
            cyclone_name=req.cyclone_name,
            preloaded=bundle,
        )
        pipeline._write_manifest(Path(req.manifest), manifest, pretty=False)
        return PredictResponse(status="ok", llm_polished=polished)
    except BaseException as exc:  # noqa: BLE001 - report to the worker, not a bare 500
        detail = f"{exc}\n{traceback.format_exc()}"
        print(f"[preparedness] /predict failed: {detail}", flush=True)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": str(exc) or exc.__class__.__name__},
        )


@app.post("/area-map")
def area_map(req: AreaMapRequest):
    """Render one area-focused metric map PNG from a run's area_metrics.json."""
    if _GIS_CACHE is None:
        detail = _LOAD_ERROR or "GIS data is still loading; retry shortly."
        return JSONResponse(status_code=503, content={"status": "error", "detail": detail})
    try:
        target = Path(req.output)
        if target.exists() and target.stat().st_size > 0:
            return {"status": "ok", "path": str(target), "cached": True}
        metrics_file = Path(req.metrics_path)
        if not metrics_file.exists():
            return JSONResponse(
                status_code=404,
                content={"status": "error", "detail": "area_metrics.json not found; re-run processing."},
            )
        metrics_by_geo = json.loads(metrics_file.read_text(encoding="utf-8"))
        path = pipeline.make_area_map_png(
            level=req.level,
            district=req.district,
            upazila=req.upazila,
            union=req.union,
            metric=req.metric,
            geo_code=req.geo_code,
            metrics_by_geo=metrics_by_geo,
            gdf_union_full=_GIS_CACHE["gdf_union_full"],
            gdf_upazila=_GIS_CACHE["gdf_upazila"],
            gdf_district=_GIS_CACHE["gdf_district"],
            output_path=target,
            lang=req.lang,
        )
        if path is None:
            return JSONResponse(
                status_code=422,
                content={"status": "error", "detail": "No boundary data matched the requested area."},
            )
        return {"status": "ok", "path": str(path), "cached": False}
    except BaseException as exc:  # noqa: BLE001
        print(f"[preparedness] /area-map failed: {exc}\n{traceback.format_exc()}", flush=True)
        return JSONResponse(status_code=500, content={"status": "error", "detail": str(exc) or exc.__class__.__name__})


@app.post("/guideline")
def guideline(req: GuidelineRequest):
    """Generate one area's structured guideline (LLM). Requires a Gemini key."""
    if not settings.llm_available:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "detail": "No Gemini key configured; structured guideline is unavailable."},
        )
    # Import lazily so a keyless deployment never pays the guidance import cost.
    from app.guidance.prompt import generate_guideline

    try:
        document = generate_guideline(
            cyclone_name=req.cyclone_name,
            context=req.context,
            cyclone_track=req.cyclone_track,
            lang=req.lang,
            lead_time_hours=req.lead_time_hours,
            track_details=req.track_details,
            data_quality_warnings=req.data_quality_warnings,
            rainfall_window_hours=req.rainfall_window_hours,
        )
        return {"document": document}
    except BaseException as exc:  # noqa: BLE001
        print(f"[preparedness] /guideline failed: {exc}\n{traceback.format_exc()}", flush=True)
        return JSONResponse(status_code=500, content={"status": "error", "detail": str(exc) or exc.__class__.__name__})


@app.post("/guideline/docx")
def guideline_docx(req: GuidelineDocxRequest):
    """Render a GuidelineDocument to a .docx and return the bytes."""
    from app.guidance.docx import build_guideline_docx

    try:
        track_bytes = None
        if req.track_map_b64:
            try:
                track_bytes = base64.b64decode(req.track_map_b64)
            except (binascii.Error, ValueError):
                track_bytes = None
        data = build_guideline_docx(req.document, track_bytes)
        name = (req.document.get("cycloneName") or "guideline").lower().replace(" ", "_")
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{name}_ibf_guideline.docx"'},
        )
    except BaseException as exc:  # noqa: BLE001
        print(f"[preparedness] /guideline/docx failed: {exc}\n{traceback.format_exc()}", flush=True)
        return JSONResponse(status_code=500, content={"status": "error", "detail": str(exc) or exc.__class__.__name__})
