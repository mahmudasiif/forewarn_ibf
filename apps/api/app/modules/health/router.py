"""Health routes — Liveness, readiness and dependency checks.

Endpoints are declared here only; all logic lives in service.py.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["Health"])

# TODO: endpoints are added feature by feature — see Documents/06-development-plan.md
