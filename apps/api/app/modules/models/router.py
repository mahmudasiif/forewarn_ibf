"""Models routes — Model registry and orchestration of runs against the model micro-services.

Endpoints are declared here only; all logic lives in service.py.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/models", tags=["Models"])

# TODO: endpoints are added feature by feature — see Documents/06-development-plan.md
