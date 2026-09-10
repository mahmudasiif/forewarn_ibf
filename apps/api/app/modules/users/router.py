"""Users routes — User profiles and self-service account operations.

Endpoints are declared here only; all logic lives in service.py.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/users", tags=["Users"])

# TODO: endpoints are added feature by feature — see Documents/06-development-plan.md
