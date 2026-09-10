"""Celery application — background jobs for the FOREWARN IBF Portal.

Jobs live in app/jobs/. Two kinds:
  * ingestion  — pull forecast/observation data from upstream providers
  * model_runs — trigger model services on a schedule and persist their output
"""
import os

from celery import Celery
from celery.schedules import crontab

celery_app = Celery(
    "forewarn",
    broker=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/1"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/2"),
    include=["app.jobs.ingestion", "app.jobs.model_runs", "app.jobs.alerts"],
)

celery_app.conf.update(
    timezone=os.getenv("TZ", "Asia/Dhaka"),
    task_track_started=True,
    task_time_limit=3600,
    worker_max_tasks_per_child=50,
)

# Scheduled work — times are Asia/Dhaka.
celery_app.conf.beat_schedule = {
    # "ingest-hazard-forecasts": {
    #     "task": "app.jobs.ingestion.ingest_forecasts",
    #     "schedule": crontab(minute=0, hour="*/6"),
    # },
}
