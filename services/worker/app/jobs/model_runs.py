"""Trigger model services and persist their outputs into models.model_runs."""
from app.celery_app import celery_app


@celery_app.task(name="app.jobs.model_runs.run_model")
def run_model(model_name: str, payload: dict | None = None) -> dict:
    """TODO: call the model service over HTTP, write models.model_runs + model_outputs."""
    return {"status": "not_implemented", "model": model_name}
