"""Model micro-service — the uniform contract every FOREWARN model implements.

    GET  /health          liveness
    GET  /info            name, version, readiness, input/output schema
    POST /predict         synchronous inference
    POST /predict/async   queue a run -> {"job_id": ...}
    GET  /jobs/{job_id}   job status + result
"""
import time
import uuid

from fastapi import FastAPI, HTTPException

from app.model.loader import is_ready, load_model
from app.model.postprocess import postprocess
from app.model.preprocess import preprocess
from app.schemas import InfoResponse, JobResponse, PredictRequest, PredictResponse
from app.settings import settings

app = FastAPI(title=f"FOREWARN model — {settings.MODEL_NAME}", version=settings.MODEL_VERSION)

# In-memory job store. Swap for Redis when async runs become real work.
_jobs: dict[str, dict] = {}


@app.on_event("startup")
async def _startup() -> None:
    load_model()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "model": settings.MODEL_NAME, "version": settings.MODEL_VERSION}


@app.get("/info", response_model=InfoResponse)
async def info() -> InfoResponse:
    return InfoResponse(
        name=settings.MODEL_NAME,
        version=settings.MODEL_VERSION,
        ready=is_ready(),
        input_schema=PredictRequest.model_json_schema(),
        output_schema=PredictResponse.model_json_schema(),
    )


@app.post("/predict", response_model=PredictResponse)
async def predict(request: PredictRequest) -> PredictResponse:
    started = time.perf_counter()
    model = load_model()
    outputs = postprocess(preprocess(request.model_dump())) | {"model": model}
    return PredictResponse(
        model_name=settings.MODEL_NAME,
        model_version=settings.MODEL_VERSION,
        outputs=outputs,
        took_ms=int((time.perf_counter() - started) * 1000),
    )


@app.post("/predict/async", response_model=JobResponse)
async def predict_async(request: PredictRequest) -> JobResponse:
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "queued", "payload": request.model_dump()}
    # TODO: hand off to a queue for long-running inference.
    return JobResponse(job_id=job_id, status="queued")


@app.get("/jobs/{job_id}", response_model=JobResponse)
async def job(job_id: str) -> JobResponse:
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Unknown job id")
    record = _jobs[job_id]
    return JobResponse(job_id=job_id, status=record["status"], result=record.get("result"))
