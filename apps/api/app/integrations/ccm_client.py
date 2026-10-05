"""CCM model client.

The CCM is not a JSON-in/JSON-out model: a run uploads a set of raw
simulation grids (tens of MB) and takes minutes, so it gets its own
multipart call rather than the shared `/predict` contract.
"""
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import UpstreamServiceError
from app.integrations.base_model_client import ModelServiceClient


class CCMClient(ModelServiceClient):
    name = "ccm"

    def __init__(self) -> None:
        super().__init__(settings.CCM_SERVICE_URL, timeout=settings.CCM_RUN_TIMEOUT)

    async def run(
        self,
        *,
        cyclone_code: str,
        files: list[tuple[str, tuple[str, bytes, str]]],
    ) -> dict[str, Any]:
        """Runs the model over one cyclone's simulation output.

        `files` is httpx's multipart shape: `(field, (filename, content, type))`.
        Errors the model raises for bad input come back as 4xx with a usable
        message, so they are surfaced rather than flattened into a generic
        upstream failure.
        """
        url = f"{self.base_url}/runs"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, data={"cyclone_code": cyclone_code}, files=files)
        except httpx.HTTPError as exc:
            raise UpstreamServiceError(
                "The CCM model service did not respond.",
                details={"url": url, "error": str(exc)},
            ) from exc

        if response.status_code >= 400:
            detail = response.text
            try:
                detail = response.json().get("detail", detail)
            except ValueError:
                pass
            raise UpstreamServiceError(
                f"CCM run rejected: {detail}",
                details={"url": url, "status": response.status_code},
            )

        return response.json()


ccm_client = CCMClient()
