"""CCM model micro-service — Module 5, Cyclone Classifier Model.

This service runs the real CCM calculation (ported from the CCM 2.9 desktop
tool, see app/model/engine.py). It is internal-only: the portal's API calls
it, browsers never do.

    GET  /health   liveness
    GET  /info     version, readiness, which files a run needs
    POST /runs     run the model over one cyclone's simulation output

A run is a few minutes of spatial joins over millions of grid points, so
/runs is deliberately synchronous but slow — the caller (the portal API)
owns the job bookkeeping and gives it a long timeout, rather than this
service keeping job state of its own.
"""
from __future__ import annotations

import logging
import shutil
import tempfile
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from app.model import loader
from app.model.engine import RESULT_COLUMNS, CycloneRawInputs, run_ccm_for_cyclone
from app.schemas import InfoResponse, RunResponse
from app.settings import settings

logger = logging.getLogger("ccm")

app = FastAPI(title=f"FOREWARN model — {settings.MODEL_NAME}", version=settings.MODEL_VERSION)

#: Track shapefiles arrive as a set of sidecar files that must keep the same
#: stem; the .shp alone is not readable.
TRACK_SIDECARS = (".shp", ".shx", ".dbf", ".prj", ".cpg")

REQUIRED_FILES = ["water_depth_xyz", "wind_speed_xyz", "rain_csv", "track (.shp/.shx/.dbf/.prj)"]
OPTIONAL_FILES = [
    "thrust_force_csv (else the three *_tf files below)",
    "water_depth_tf_xyz",
    "wind_speed_tf_xyz",
    "depth_avg_velocity_tf_xyz",
]


@app.on_event("startup")
async def _startup() -> None:
    try:
        loader.load()
        logger.info("ccm reference data loaded from %s", settings.CCM_DATA_DIR)
    except Exception:
        # Don't take the container down — /health stays up and /info reports
        # the problem, which is easier to diagnose than a crash loop.
        logger.exception("ccm reference data failed to load")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "model": settings.MODEL_NAME, "version": settings.MODEL_VERSION}


@app.get("/info", response_model=InfoResponse)
async def info() -> InfoResponse:
    return InfoResponse(
        name=settings.MODEL_NAME,
        version=settings.MODEL_VERSION,
        ready=loader.is_ready(),
        required_files=REQUIRED_FILES,
        optional_files=OPTIONAL_FILES,
        result_columns=RESULT_COLUMNS,
    )


async def _save(upload: UploadFile | None, directory: Path, name: str | None = None) -> Path | None:
    """Streams one upload to disk. Returns None for an omitted optional file."""
    if upload is None or not upload.filename:
        return None
    target = directory / (name or Path(upload.filename).name)
    with target.open("wb") as handle:
        shutil.copyfileobj(upload.file, handle)
    return target


@app.post("/runs", response_model=RunResponse)
async def create_run(
    cyclone_code: str = Form(...),
    water_depth_xyz: UploadFile = File(...),
    wind_speed_xyz: UploadFile = File(...),
    rain_csv: UploadFile = File(...),
    track_shp: UploadFile = File(...),
    track_shx: UploadFile = File(...),
    track_dbf: UploadFile = File(...),
    track_prj: UploadFile | None = File(None),
    track_cpg: UploadFile | None = File(None),
    thrust_force_csv: UploadFile | None = File(None),
    water_depth_tf_xyz: UploadFile | None = File(None),
    wind_speed_tf_xyz: UploadFile | None = File(None),
    depth_avg_velocity_tf_xyz: UploadFile | None = File(None),
) -> RunResponse:
    """Runs the CCM over one cyclone's simulation output.

    Everything is written to a scratch directory, computed, and thrown away —
    this service stores nothing. Persisting the result is the portal API's
    job, which is also what decides whether a run is kept.
    """
    if not loader.is_ready():
        raise HTTPException(
            status_code=503,
            detail=(
                "CCM reference data is not loaded "
                f"(expected at {settings.CCM_DATA_DIR}): {loader.last_error()}"
            ),
        )

    started = time.perf_counter()
    settings.CCM_RUN_DIR.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix=f"{cyclone_code}-", dir=settings.CCM_RUN_DIR))

    try:
        # The track sidecars must share one stem for the shapefile to open.
        stem = "track"
        await _save(track_shp, workdir, f"{stem}.shp")
        await _save(track_shx, workdir, f"{stem}.shx")
        await _save(track_dbf, workdir, f"{stem}.dbf")
        await _save(track_prj, workdir, f"{stem}.prj")
        await _save(track_cpg, workdir, f"{stem}.cpg")

        inputs = CycloneRawInputs(
            water_depth_xyz=await _save(water_depth_xyz, workdir, "water_depth.xyz"),
            wind_speed_xyz=await _save(wind_speed_xyz, workdir, "wind_speed.xyz"),
            rain_csv=await _save(rain_csv, workdir, "rain.csv"),
            track_shp=workdir / f"{stem}.shp",
            thrust_force_csv=await _save(thrust_force_csv, workdir, "thrust_force.csv"),
            water_depth_tf_xyz=await _save(water_depth_tf_xyz, workdir, "water_depth_tf.xyz"),
            wind_speed_tf_xyz=await _save(wind_speed_tf_xyz, workdir, "wind_speed_tf.xyz"),
            depth_avg_velocity_tf_xyz=await _save(
                depth_avg_velocity_tf_xyz, workdir, "depth_avg_velocity_tf.xyz"
            ),
        )

        if inputs.thrust_force_csv is None and not (
            inputs.water_depth_tf_xyz
            and inputs.wind_speed_tf_xyz
            and inputs.depth_avg_velocity_tf_xyz
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    "Provide either thrust_force_csv, or all three of "
                    "water_depth_tf_xyz, wind_speed_tf_xyz and depth_avg_velocity_tf_xyz."
                ),
            )

        logger.info("ccm run starting: %s", cyclone_code)
        try:
            result_df, track_gdf = run_ccm_for_cyclone(loader.load(), inputs)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            # Almost always malformed input (wrong header rows, missing
            # columns, a track in the wrong projection). Hand the caller the
            # real message — it is the only useful thing to show an operator.
            logger.exception("ccm run failed: %s", cyclone_code)
            raise HTTPException(
                status_code=422, detail=f"CCM run failed: {type(exc).__name__}: {exc}"
            ) from exc

        rows = result_df.where(result_df.notna(), None).to_dict(orient="records")
        track = None
        if track_gdf is not None and len(track_gdf) > 0:
            if track_gdf.crs is not None and track_gdf.crs.to_epsg() != 4326:
                track_gdf = track_gdf.to_crs(4326)
            track = track_gdf.__geo_interface__

        took_ms = int((time.perf_counter() - started) * 1000)
        logger.info("ccm run finished: %s — %d unions in %d ms", cyclone_code, len(rows), took_ms)

        return RunResponse(
            model_name=settings.MODEL_NAME,
            model_version=settings.MODEL_VERSION,
            cyclone_code=cyclone_code,
            rows=rows,
            track=track,
            row_count=len(rows),
            took_ms=took_ms,
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
