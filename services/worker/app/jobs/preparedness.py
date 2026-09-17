"""Run the Preparedness Guidance pipeline for one uploaded forecast.

Flow: mark the run running -> pull inputs from object storage onto the shared
`prep-runs` volume -> call the preparedness model service `/predict` (which writes
maps/spreadsheets to that same volume) -> upload the artifacts to object storage
-> record the summary + guideline + artifact keys on the run row.

The worker owns persistence; the model service owns the model. This module never
imports model code — it only speaks HTTP + SQL + S3.
"""
from __future__ import annotations

import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import create_engine, text

from app import storage
from app.celery_app import celery_app

SVC_URL = os.getenv("PREPAREDNESS_SERVICE_URL", "http://preparedness:8000")
SVC_TIMEOUT = int(os.getenv("PREPAREDNESS_REQUEST_TIMEOUT", "1200"))
RUNS_ROOT = Path(os.getenv("PREPAREDNESS_RUNS_DIR", "/runs"))

#: manifest key -> (download label, MIME type). Only these are surfaced to users.
ARTIFACT_MAP: dict[str, tuple[str, str]] = {
    "risk_map_html": ("Risk Map (HTML)", "text/html"),
    "wind_intensity_map_html": ("Wind Intensity Map (HTML)", "text/html"),
    "storm_surge_map_html": ("Storm Surge Map (HTML)", "text/html"),
    "rainfall_risk_map_html": ("Rainfall Risk Map (HTML)", "text/html"),
    "track_map_jpg": ("Cyclone Track Map (JPEG)", "image/jpeg"),
    "risk_classification_excel": ("Risk Classification (Excel)", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "housing_damage_excel": ("Housing Damage (Excel)", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "rainfall_evacuation_excel": ("Rainfall Evacuation (Excel)", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "guideline_path": ("Guideline (Markdown)", "text/markdown"),
    "material_needs_csv": ("Material Needs (CSV)", "text/csv"),
    "risk_classification_csv": ("Risk Classification (CSV)", "text/csv"),
    "housing_damage_csv": ("Housing Damage (CSV)", "text/csv"),
    "rainfall_evacuation_csv": ("Rainfall Evacuation (CSV)", "text/csv"),
}

#: manifest keys copied into the run's `summary` JSONB for the UI stat tiles.
SUMMARY_KEYS = (
    "summary",
    "risk_class_summary",
    "overall_damaged_types",
    "top_risk_upazilas_extended",
    "top_rain_upazilas_extended",
    "max_wind_record",
    "max_rain_record",
    "max_storm_surge_record",
    "cyclone_track",
    "input_type",
    "input_metadata",
    "damage_model",
    "data_quality_warnings",
    "data_quality_warnings_en",
)


def _engine():
    # Celery tasks are synchronous; use a sync driver against the async URL.
    url = os.getenv("DATABASE_URL", "postgresql+asyncpg://forewarn:change_me@db:5432/forewarn")
    return create_engine(url.replace("+asyncpg", "+psycopg2"), pool_pre_ping=True)


def _now():
    return datetime.now(timezone.utc)


#: columns whose Python value is a JSON string and must be cast text -> jsonb.
_JSONB_COLS = {"summary", "artifacts", "input_files"}


def _update(engine, run_id: int, **fields) -> None:
    if not fields:
        return
    cols = ", ".join(
        (f"{k} = CAST(:{k} AS jsonb)" if k in _JSONB_COLS else f"{k} = :{k}") for k in fields
    )
    with engine.begin() as conn:
        conn.execute(
            text(f"UPDATE preparedness.runs SET {cols} WHERE id = :id"),
            {**fields, "id": run_id},
        )


def _fetch(engine, run_id: int) -> dict:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT input_files, damage_model, cyclone_name, polished "
                "FROM preparedness.runs WHERE id = :id"
            ),
            {"id": run_id},
        ).mappings().first()
    if row is None:
        raise RuntimeError(f"preparedness run {run_id} not found")
    return dict(row)


@celery_app.task(name="app.jobs.preparedness.run_preparedness")
def run_preparedness(run_id: int) -> dict:
    engine = _engine()
    run_dir = RUNS_ROOT / str(run_id)
    in_dir = run_dir / "in"
    out_dir = run_dir / "out"
    _update(engine, run_id, status="running", started_at=_now())

    try:
        row = _fetch(engine, run_id)
        input_files = row["input_files"] or {}
        if "wind" not in input_files:
            raise RuntimeError("run has no wind input")

        in_dir.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(parents=True, exist_ok=True)

        local: dict[str, str] = {}
        for role, meta in input_files.items():
            dest = in_dir / meta["filename"]
            storage.download_file(meta["key"], str(dest))
            local[role] = str(dest)

        manifest_path = out_dir / "manifest.json"
        payload = {
            "input": local["wind"],
            "output": str(out_dir),
            "manifest": str(manifest_path),
            "rainfall": local.get("rainfall"),
            "storm_surge": local.get("storm_surge"),
            "damage_model": row["damage_model"],
            "cyclone_name": row["cyclone_name"],
            "polished": bool(row["polished"]),
        }

        resp = httpx.post(f"{SVC_URL}/predict", json=payload, timeout=SVC_TIMEOUT)
        if resp.status_code != 200:
            detail = resp.text
            try:
                detail = resp.json().get("detail", detail)
            except Exception:  # noqa: BLE001
                pass
            raise RuntimeError(f"model service /predict failed ({resp.status_code}): {detail}")
        llm_polished = bool(resp.json().get("llm_polished", False))

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        artifacts = []
        for key, (label, ctype) in ARTIFACT_MAP.items():
            path = manifest.get(key)
            if not path:
                continue
            p = Path(path)
            if not p.exists() or p.stat().st_size == 0:
                continue
            name = p.name
            okey = f"preparedness/{run_id}/artifacts/{name}"
            storage.put_file(okey, str(p), ctype)
            artifacts.append(
                {"label": label, "name": name, "key": okey,
                 "content_type": ctype, "size": p.stat().st_size}
            )

        summary = {k: manifest.get(k) for k in SUMMARY_KEYS if manifest.get(k) is not None}

        # Per-area data for the interactive area explorer + guideline generation.
        # This is large (~1500 unions), so it lives in object storage, not the DB.
        contexts = {
            "analysis_contexts": manifest.get("analysis_contexts", []),
            "analysis_options": manifest.get("analysis_options", []),
            "cyclone_track": manifest.get("cyclone_track"),
            "cyclone_name": row["cyclone_name"],
            "rainfall_window_hours": (manifest.get("input_metadata") or {}).get("rainfall_accumulation_hours"),
            "data_quality_warnings": manifest.get("data_quality_warnings"),
            "data_quality_warnings_en": manifest.get("data_quality_warnings_en"),
        }
        contexts_path = run_dir / "contexts.json"
        contexts_path.write_text(json.dumps(contexts, ensure_ascii=False), encoding="utf-8")
        storage.put_file(f"preparedness/{run_id}/contexts.json", str(contexts_path), "application/json")

        _update(
            engine,
            run_id,
            status="succeeded",
            finished_at=_now(),
            summary=json.dumps(summary),
            guideline_markdown=manifest.get("guideline_markdown"),
            artifacts=json.dumps(artifacts),
            llm_polished=llm_polished,
        )
        return {"status": "succeeded", "run_id": run_id, "artifacts": len(artifacts)}

    except Exception as exc:  # noqa: BLE001 - record failure on the run, do not retry
        detail = f"{exc}\n{traceback.format_exc()}"
        print(f"[preparedness job] run {run_id} failed: {detail}", flush=True)
        _update(engine, run_id, status="failed", finished_at=_now(), error=str(exc))
        return {"status": "failed", "run_id": run_id, "error": str(exc)}
    finally:
        # Keep the working dir: area_metrics.json + boundaries stay on the shared
        # `prep-runs` volume so on-demand /area-map and /guideline can reuse them.
        # (A future cleanup task should prune old /runs/<id> directories.)
        engine.dispose()
