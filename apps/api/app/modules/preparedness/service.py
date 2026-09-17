"""Preparedness business logic — create/list/read runs.

The heavy lifting (calling the model service, storing artifacts) happens in the
Celery worker; this module owns the run records and their lifecycle from the
API's side.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.preparedness.models import Run


async def create_run(
    db: AsyncSession,
    *,
    cyclone_name: str,
    damage_model: str,
    polished: bool,
    input_files: dict,
) -> Run:
    run = Run(
        cyclone_name=cyclone_name,
        damage_model=damage_model,
        polished=polished,
        input_files=input_files,
        status="queued",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


async def list_runs(db: AsyncSession, limit: int = 100) -> list[Run]:
    rows = await db.execute(select(Run).order_by(Run.created_at.desc()).limit(limit))
    return list(rows.scalars().all())


async def get_run(db: AsyncSession, run_id: int) -> Run:
    run = await db.get(Run, run_id)
    if run is None:
        raise NotFoundError(f"No preparedness run with id {run_id}.")
    return run
