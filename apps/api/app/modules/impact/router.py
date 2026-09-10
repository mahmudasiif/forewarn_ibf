"""Impact routes — Vulnerability, exposure metrics and the impact matrix that turns hazard into impact.

Endpoints are declared here only; all logic lives in service.py.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/impact", tags=["Impact"])

# TODO: endpoints are added feature by feature — see Documents/06-development-plan.md
