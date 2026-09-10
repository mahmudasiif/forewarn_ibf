"""The contract this service exposes. Replace the placeholders with the real shapes."""
from typing import Any

from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    """TODO: describe the real inputs this model needs."""

    inputs: dict[str, Any] = Field(default_factory=dict)


class PredictResponse(BaseModel):
    """TODO: describe the real outputs this model produces."""

    model_name: str
    model_version: str
    outputs: dict[str, Any] = Field(default_factory=dict)
    took_ms: int | None = None


class InfoResponse(BaseModel):
    name: str
    version: str
    ready: bool
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


class JobResponse(BaseModel):
    job_id: str
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
