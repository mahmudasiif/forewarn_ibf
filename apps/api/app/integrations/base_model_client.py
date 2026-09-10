"""Shared HTTP client for every model micro-service.

Each model gets a thin subclass (see ccm_client.py). The core API never imports
model code — it only speaks this contract over HTTP:

    GET  /health           -> liveness
    GET  /info             -> name, version, input/output schema
    POST /predict          -> synchronous inference
    POST /predict/async    -> {"job_id": ...}
    GET  /jobs/{job_id}    -> job status + result
"""
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import UpstreamServiceError


class ModelServiceClient:
    name: str = "base"

    def __init__(self, base_url: str, timeout: int | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout or settings.MODEL_REQUEST_TIMEOUT

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(method, url, **kwargs)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            raise UpstreamServiceError(
                f"Model service '{self.name}' failed.", details={"url": url, "error": str(exc)}
            ) from exc

    async def health(self) -> dict:
        return await self._request("GET", "/health")

    async def info(self) -> dict:
        return await self._request("GET", "/info")

    async def predict(self, payload: dict) -> dict:
        return await self._request("POST", "/predict", json=payload)

    async def predict_async(self, payload: dict) -> dict:
        return await self._request("POST", "/predict/async", json=payload)

    async def job(self, job_id: str) -> dict:
        return await self._request("GET", f"/jobs/{job_id}")
