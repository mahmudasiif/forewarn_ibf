"""Reports routes — Generated reports, attachments and exports.

Endpoints are declared here only; all logic lives in service.py.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/reports", tags=["Reports"])

# TODO: endpoints are added feature by feature — see Documents/06-development-plan.md
