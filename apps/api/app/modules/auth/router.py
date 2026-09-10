"""Auth routes — Login, logout, token refresh, password reset.

Endpoints are declared here only; all logic lives in service.py.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["Auth"])

# TODO: endpoints are added feature by feature — see Documents/06-development-plan.md
