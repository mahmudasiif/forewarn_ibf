"""The v1 API router — every module plugs in here and only here."""
from fastapi import APIRouter

from app.modules.admin.router import router as admin_router
from app.modules.alerts.router import router as alerts_router
from app.modules.auth.router import router as auth_router
from app.modules.ccm.router import router as ccm_router
from app.modules.dfrm.router import router as dfrm_router
from app.modules.geo.router import router as geo_router
from app.modules.hazards.router import router as hazards_router
from app.modules.health.router import router as health_router
from app.modules.impact.router import router as impact_router
from app.modules.models.router import router as models_router
from app.modules.preparedness.router import router as preparedness_router
from app.modules.reports.router import router as reports_router
from app.modules.users.router import router as users_router

api_router = APIRouter()

for r in (
    health_router,
    auth_router,
    users_router,
    admin_router,
    geo_router,
    hazards_router,
    impact_router,
    models_router,
    ccm_router,
    preparedness_router,
    dfrm_router,
    alerts_router,
    reports_router,
):
    api_router.include_router(r)
