"""DFRM request bodies — Module 7, Flood Risk. Map/warning responses are passed
through from the model service (GeoJSON / warning tables) unchanged; the run
history is the portal's own."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Level = Literal["District", "Upazilla", "Union", "Village"]
MapLayer = Literal["Inundation", "Hazard", "Risk", "Vulnerability"]
WLKind = Literal["WL", "DL"]


class MapBody(BaseModel):
    level: Level = "Union"
    area_id: str
    layer: MapLayer = "Inundation"
    water_level: float = Field(..., description="Water level (m); absolute or above-danger per wl_kind.")
    wl_kind: WLKind = "WL"
    limb: str = "Flood Increasing"
    simplify: float = 0.0


class WarningBody(BaseModel):
    level: Level = "Union"
    area_id: str
    water_level: float = Field(..., description="Water level (m); absolute or above-danger per wl_kind.")
    wl_kind: WLKind = "WL"
    limb: str = "Flood Increasing"
    date: str | None = None


class RunSummary(BaseModel):
    """One recorded DFRM query, for the run history."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    level: str
    area_id: str
    area_name: str
    layer: str
    water_level: float
    wl_kind: str
    limb: str
    date: str | None = None
    river: str
    station: str
    return_period: float | None = None
    summary: dict | None = None
    created_at: datetime
