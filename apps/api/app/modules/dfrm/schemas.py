"""DFRM request bodies — Module 7, Flood Risk. Map/warning responses are passed
through from the model service (GeoJSON / warning tables) unchanged; the run
history is the portal's own."""
from datetime import date, datetime
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
    #: whether to record this query in the audit trail (the forecast page sets
    #: this false for its on-demand upazila/union maps so they don't inflate it)
    record: bool = True


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


# --------------------------------------------------------------- automated forecast


class ForecastDayOut(BaseModel):
    """One forecast day for one area, with a URL to stream its map GeoJSON."""

    id: int
    day_index: int
    forecast_date: date
    water_level: float
    prev_water_level: float | None = None
    limb: str
    phase: str
    area_id: str
    area_name: str
    layer: str
    river: str
    station: str
    hydrograph_day: str | None = None
    return_period: float | None = None
    feature_count: int | None = None
    metric_unit: str | None = None
    metric_min: float | None = None
    metric_max: float | None = None
    status: str
    #: GET this to stream the day's full /map response (None if the run failed)
    map_url: str | None = None


class ForecastSetOut(BaseModel):
    """One daily automated 5-day forecast set (FFWC-driven), with its day rows."""

    id: int
    run_date: date
    source: str
    station: str
    danger_level: float
    observed_wl: float | None = None
    layer: str
    level: str
    pulled_at: datetime | None = None
    created_at: datetime
    days: list[ForecastDayOut]
