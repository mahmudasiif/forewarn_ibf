"""Alerts routes — Triggers, thresholds, alert generation and delivery.

Endpoints are declared here only; all logic lives in service.py.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/alerts", tags=["Alerts"])

# TODO: endpoints are added feature by feature — see Documents/06-development-plan.md
