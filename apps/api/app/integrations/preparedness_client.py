"""Preparedness Guidance model client.

Health/info use the shared model-service contract. The actual run is driven by
the Celery worker (a long, path-based `/predict`), not the request path, so it is
not exposed here.
"""
from app.core.config import settings
from app.integrations.base_model_client import ModelServiceClient


class PreparednessClient(ModelServiceClient):
    name = "preparedness"

    def __init__(self) -> None:
        super().__init__(
            settings.PREPAREDNESS_SERVICE_URL,
            timeout=settings.PREPAREDNESS_REQUEST_TIMEOUT,
        )


preparedness_client = PreparednessClient()
