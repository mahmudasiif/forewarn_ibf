from typing import Any, Literal

from pydantic import BaseModel, Field

Level = Literal["District", "Upazilla", "Union", "Village"]
MapLayer = Literal["Inundation", "Hazard", "Risk", "Vulnerability"]


# --- uniform model contract ------------------------------------------------ #


class InfoResponse(BaseModel):
    name: str
    version: str
    ready: bool
    input_schema: dict
    output_schema: dict


class PredictRequest(BaseModel):
    """A one-shot map or warning request (the service's real work)."""

    kind: Literal["map", "warning"] = "map"
    level: Level = "Union"
    area_id: str
    layer: MapLayer = "Inundation"
    water_level: float
    limb: str = "Flood Increasing"
    date: str | None = None
    wl_kind: Literal["WL", "DL"] = "WL"


class PredictResponse(BaseModel):
    model_name: str
    model_version: str
    outputs: dict
    took_ms: int


class JobResponse(BaseModel):
    job_id: str
    status: str
    result: dict | None = None


# --- domain requests ------------------------------------------------------- #


class MapRequest(BaseModel):
    level: Level
    area_id: str
    layer: MapLayer = "Inundation"
    water_level: float = Field(..., description="Water level (m); see wl_kind.")
    wl_kind: Literal["WL", "DL"] = "WL"
    limb: str = "Flood Increasing"
    simplify: float = 0.0


class WarningRequest(BaseModel):
    level: Level
    area_id: str
    water_level: float = Field(..., description="Water level (m); see wl_kind.")
    wl_kind: Literal["WL", "DL"] = "WL"
    limb: str = "Flood Increasing"
    date: str | None = None


class ReturnPeriodInfo(BaseModel):
    water_level: float
    return_period: float | None


class MapResponse(BaseModel):
    level: str
    area_id: str
    area_name: str
    layer: str
    river: str
    station: str
    danger_level: float
    day: str
    limb: str
    water_level: float
    return_period: float | None
    metric_min: float | None
    metric_max: float | None
    metric_unit: str
    bounds: list[float]
    feature_count: int
    features: list[dict[str, Any]]
    rivers: dict[str, Any]
    context: dict[str, Any]
