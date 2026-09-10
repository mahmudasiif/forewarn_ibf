"""Admin routes — Role/permission management and system settings.

Endpoints are declared here only; all logic lives in service.py.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/admin", tags=["Admin"])

# TODO: endpoints are added feature by feature — see Documents/06-development-plan.md
