"""Geo routes — Administrative units, exposure layers and map geometry (PostGIS).

Endpoints are declared here only; all logic lives in service.py.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/geo", tags=["Geo"])

# TODO: endpoints are added feature by feature — see Documents/06-development-plan.md
