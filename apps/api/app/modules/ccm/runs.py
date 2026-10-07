"""Starting and tracking CCM model runs.

A run is: raw simulation output in -> the model service computes one row per
union -> those rows replace that cyclone's results in the database, after
which every existing CCM endpoint (map, table, CSV export) serves them with
no further work.

The run itself takes minutes, so the HTTP request that starts it returns as
soon as the row is recorded and the files are in hand. The work continues in
a background task; the browser polls the run row. A closed tab does not
cancel or lose anything.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal
from app.core.logging import logger
from app.integrations.ccm_client import ccm_client
from app.modules.ccm.ingest import persist_run_results

#: Multipart field name -> whether the model requires it.
RUN_FILE_FIELDS: dict[str, bool] = {
    "water_depth_xyz": True,
    "wind_speed_xyz": True,
    "rain_csv": True,
    "track_shp": True,
    "track_shx": True,
    "track_dbf": True,
    "track_prj": False,
    "track_cpg": False,
    "thrust_force_csv": False,
    "water_depth_tf_xyz": False,
    "wind_speed_tf_xyz": False,
    "depth_avg_velocity_tf_xyz": False,
}


async def create_run(db: AsyncSession, *, code: str, meta: dict[str, Any], manifest: dict) -> int:
    """Records a queued run and returns its id."""
    return (
        await db.execute(
            text(
                """
                INSERT INTO ccm.runs (cyclone_code, status, inputs)
                VALUES (:code, 'queued', CAST(:inputs AS jsonb))
                RETURNING id
                """
            ),
            {
                "code": code,
                "inputs": json.dumps({"meta": meta, "files": manifest}),
            },
        )
    ).scalar_one()


async def _set_status(db: AsyncSession, run_id: int, **fields: Any) -> None:
    assignments = ", ".join(f"{k} = :{k}" for k in fields)
    await db.execute(
        text(f"UPDATE ccm.runs SET {assignments} WHERE id = :id"), {"id": run_id, **fields}
    )
    await db.commit()


async def execute_run(
    run_id: int,
    *,
    code: str,
    meta: dict[str, Any],
    files: list[tuple[str, tuple[str, bytes, str]]],
) -> None:
    """Runs the model and stores the result. Never raises — a failure is
    recorded on the run row, which is what the operator sees."""
    async with SessionLocal() as db:
        await _set_status(db, run_id, status="running")

        try:
            payload = await ccm_client.run(cyclone_code=code, files=files)
        except Exception as exc:  # noqa: BLE001 — the message is the deliverable
            logger.warning("ccm.run.failed", run_id=run_id, code=code, error=str(exc))
            await _set_status(
                db,
                run_id,
                status="failed",
                error=str(exc),
                finished_at=datetime.now(UTC),
            )
            return

        try:
            cyclone_id, written = await persist_run_results(
                db,
                code=code,
                rows=payload.get("rows", []),
                meta=meta,
                track=payload.get("track"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("ccm.run.persist_failed", run_id=run_id, code=code)
            await _set_status(
                db,
                run_id,
                status="failed",
                error=f"The model ran, but its results could not be stored: {exc}",
                finished_at=datetime.now(UTC),
            )
            return

        logger.info("ccm.run.succeeded", run_id=run_id, code=code, rows=written)
        await _set_status(
            db,
            run_id,
            status="succeeded",
            cyclone_id=cyclone_id,
            row_count=written,
            took_ms=payload.get("took_ms"),
            finished_at=datetime.now(UTC),
        )


async def list_runs(db: AsyncSession, limit: int = 20) -> list[dict]:
    rows = (
        await db.execute(
            text(
                """
                SELECT r.id, r.cyclone_code, r.status, r.cyclone_id, r.row_count,
                       r.error, r.took_ms, r.created_at, r.finished_at, c.name AS cyclone_name
                FROM ccm.runs r
                LEFT JOIN ccm.cyclones c ON c.id = r.cyclone_id
                ORDER BY r.created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
    ).mappings()
    return [dict(r) for r in rows]


async def get_run(db: AsyncSession, run_id: int) -> dict | None:
    row = (
        await db.execute(
            text(
                """
                SELECT r.id, r.cyclone_code, r.status, r.cyclone_id, r.row_count,
                       r.error, r.took_ms, r.created_at, r.finished_at, c.name AS cyclone_name
                FROM ccm.runs r
                LEFT JOIN ccm.cyclones c ON c.id = r.cyclone_id
                WHERE r.id = :id
                """
            ),
            {"id": run_id},
        )
    ).mappings().first()
    return dict(row) if row else None
