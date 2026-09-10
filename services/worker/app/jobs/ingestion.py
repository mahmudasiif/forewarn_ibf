"""Pull data from upstream providers into ops.ingestion_runs + the hazard schema."""
from app.celery_app import celery_app


@celery_app.task(name="app.jobs.ingestion.ingest_forecasts")
def ingest_forecasts(source: str | None = None) -> dict:
    """TODO: fetch, validate, store. Record every attempt in ops.ingestion_runs."""
    return {"status": "not_implemented", "source": source}
