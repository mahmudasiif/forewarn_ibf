"""Hazards routes — Hazard types, observed events and hazard forecasts.

Endpoints are declared here only; all logic lives in service.py.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/hazards", tags=["Hazards"])

# TODO: endpoints are added feature by feature — see Documents/06-development-plan.md
