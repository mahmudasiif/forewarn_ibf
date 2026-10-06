"""The contract this service exposes.

The CCM is not an inference model — it is a deterministic geospatial
calculation over one cyclone's simulation output. A "prediction" here is a
*run*: raw storm-surge/wind/rain grids in, one row per coastal union out.
"""
from typing import Any

from pydantic import BaseModel, Field


class RunResponse(BaseModel):
    """One completed CCM run."""

    model_name: str
    model_version: str
    cyclone_code: str
    #: One dict per union, keyed by the CCM result column names
    #: (same headers the desktop tool writes to Cyclone_Info/<name>.csv).
    rows: list[dict[str, Any]] = Field(default_factory=list)
    #: The cyclone track as GeoJSON, for drawing on the portal map.
    track: dict[str, Any] | None = None
    row_count: int = 0
    took_ms: int | None = None


class InfoResponse(BaseModel):
    name: str
    version: str
    ready: bool
    #: Which raw files a run needs, and which columns it returns.
    required_files: list[str]
    optional_files: list[str]
    result_columns: list[str]


class ErrorResponse(BaseModel):
    detail: str
