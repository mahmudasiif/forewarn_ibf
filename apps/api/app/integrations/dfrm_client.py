"""DFRM model client — Module 7, Flood Risk.

The core API never imports the model code; it speaks the model-service HTTP
contract plus DFRM's three domain endpoints (``/areas``, ``/map``, ``/warning``).
"""
from app.core.config import settings
from app.integrations.base_model_client import ModelServiceClient


class DFRMClient(ModelServiceClient):
    name = "dfrm"

    def __init__(self) -> None:
        super().__init__(settings.DFRM_SERVICE_URL, timeout=settings.DFRM_REQUEST_TIMEOUT)

    async def areas(self) -> dict:
        return await self._request("GET", "/areas")

    async def map_layer(self, payload: dict) -> dict:
        return await self._request("POST", "/map", json=payload)

    async def warning(self, payload: dict) -> dict:
        return await self._request("POST", "/warning", json=payload)


dfrm_client = DFRMClient()
