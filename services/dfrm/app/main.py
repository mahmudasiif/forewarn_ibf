"""DFRM model micro-service — Module 7, Flood Risk.

Implements the uniform FOREWARN model contract:

    GET  /health          liveness
    GET  /info            name, version, readiness, input/output schema
    POST /predict         synchronous inference (map or warning)
    POST /predict/async   queue a run -> {"job_id": ...}
    GET  /jobs/{job_id}   job status + result

plus the domain endpoints the portal drives directly:

    GET  /areas           the District -> Upazilla -> Union -> Village picker
    POST /map             a graded flood layer as a GeoJSON choropleth
    POST /warning         the per-area flood warning table
"""
import time
import uuid

from fastapi import FastAPI, HTTPException

from app.model import engine
from app.schemas import (
    InfoResponse,
    JobResponse,
    MapRequest,
    MapResponse,
    PredictRequest,
    PredictResponse,
    WarningRequest,
)
from app.settings import settings

app = FastAPI(title=f"FOREWARN model — {settings.MODEL_NAME}", version=settings.MODEL_VERSION)

_jobs: dict[str, dict] = {}


@app.on_event("startup")
async def _startup() -> None:
    if engine.is_ready():
        engine.warm_cache()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "model": settings.MODEL_NAME, "version": settings.MODEL_VERSION}


@app.get("/info", response_model=InfoResponse)
async def info() -> InfoResponse:
    return InfoResponse(
        name=settings.MODEL_NAME,
        version=settings.MODEL_VERSION,
        ready=engine.is_ready(),
        input_schema=PredictRequest.model_json_schema(),
        output_schema=PredictResponse.model_json_schema(),
    )


def _run_predict(req: PredictRequest) -> dict:
    wl = engine.resolve_water_level(req.water_level, req.wl_kind)
    if req.kind == "warning":
        return engine.warning(
            level=req.level, area_id=req.area_id, water_level=wl, limb=req.limb, date=req.date
        )
    return engine.map_layer(
        level=req.level, area_id=req.area_id, layer=req.layer, water_level=wl, limb=req.limb
    )


@app.post("/predict", response_model=PredictResponse)
async def predict(request: PredictRequest) -> PredictResponse:
    started = time.perf_counter()
    try:
        outputs = _run_predict(request)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PredictResponse(
        model_name=settings.MODEL_NAME,
        model_version=settings.MODEL_VERSION,
        outputs=outputs,
        took_ms=int((time.perf_counter() - started) * 1000),
    )


@app.post("/predict/async", response_model=JobResponse)
async def predict_async(request: PredictRequest) -> JobResponse:
    job_id = str(uuid.uuid4())
    try:
        result = _run_predict(request)
        _jobs[job_id] = {"status": "succeeded", "result": result}
    except (LookupError, ValueError) as exc:
        _jobs[job_id] = {"status": "failed", "result": {"error": str(exc)}}
    return JobResponse(job_id=job_id, status=_jobs[job_id]["status"], result=_jobs[job_id]["result"])


@app.get("/jobs/{job_id}", response_model=JobResponse)
async def job(job_id: str) -> JobResponse:
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Unknown job id")
    record = _jobs[job_id]
    return JobResponse(job_id=job_id, status=record["status"], result=record.get("result"))


# --- domain endpoints ------------------------------------------------------ #


@app.get("/areas")
async def areas() -> dict:
    """The cascading admin picker + stations / limbs / layers for the UI."""
    return engine.area_tree()


@app.post("/map", response_model=MapResponse)
async def map_(request: MapRequest) -> dict:
    wl = engine.resolve_water_level(request.water_level, request.wl_kind)
    try:
        return engine.map_layer(
            level=request.level,
            area_id=request.area_id,
            layer=request.layer,
            water_level=wl,
            limb=request.limb,
            simplify=request.simplify,
        )
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/warning")
async def warning_(request: WarningRequest) -> dict:
    wl = engine.resolve_water_level(request.water_level, request.wl_kind)
    try:
        return engine.warning(
            level=request.level,
            area_id=request.area_id,
            water_level=wl,
            limb=request.limb,
            date=request.date,
        )
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
