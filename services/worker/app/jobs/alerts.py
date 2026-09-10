"""Evaluate triggers against the latest impact forecasts and raise alerts."""
from app.celery_app import celery_app


@celery_app.task(name="app.jobs.alerts.evaluate_triggers")
def evaluate_triggers() -> dict:
    """TODO: compare impact forecasts to alerts.thresholds, create alerts, queue delivery."""
    return {"status": "not_implemented"}
