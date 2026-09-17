"""Celery client for the API side.

The API does not run tasks — it only *enqueues* them onto the same broker the
worker (services/worker) consumes. Tasks are addressed by name so the API never
imports worker code.
"""
from celery import Celery

from app.core.config import settings

celery_client = Celery("forewarn-api", broker=settings.CELERY_BROKER_URL)


def enqueue_preparedness(run_id: int) -> None:
    celery_client.send_task("app.jobs.preparedness.run_preparedness", args=[run_id])
