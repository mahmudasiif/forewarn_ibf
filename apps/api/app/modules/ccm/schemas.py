"""CCM request/response models — the API contract for this module."""
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

AdminLevel = Literal["union", "upazila", "district", "division"]
Operator = Literal["gte", "gt", "lte", "lt", "eq"]
#: How a trigger threshold is read. "value" compares the metric to the number
#: given; "return_period" reads the number as years and keeps only the unions
#: where this cyclone exceeds their own 1-in-T-year event.
ThresholdMode = Literal["value", "return_period"]


class CycloneSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    event_date: date | None = None
    landfall_location: str | None = None
    max_wind_speed: float | None = None
    cyclone_type: str
    source: str
    model_version: str
    imported_at: datetime


class CycloneDetail(CycloneSummary):
    remark: str | None = None
    notes: str | None = None
    union_count: int = 0
    #: headline totals across every union, for the stat tiles
    totals: dict[str, float] = Field(default_factory=dict)


class MetricInfo(BaseModel):
    key: str
    label: str
    unit: str
    aggregation: str
    mappable: bool
    description: str = ""


class LocationOption(BaseModel):
    """One entry in a cascading Division → District → Upazila picker."""

    value: str
    label: str
    parent: str | None = None


class ResultRow(BaseModel):
    """A single row of the results table, at whatever level was requested."""

    model_config = ConfigDict(from_attributes=True)

    union_geo: int | None = None
    division: str
    district: str | None = None
    upazila: str | None = None
    union_name: str | None = None

    surge_height_m: float | None = None
    wind_speed_kmh: float | None = None
    thrust_force: float | None = None
    rainfall_72h_mm: float | None = None

    polder_damage: str | None = None
    structure_damage: str | None = None
    agri_land_damage: str | None = None

    flooded_area_km2: float | None = None
    flooded_area_pct: float | None = None
    house_damage_million_bdt: float | None = None
    affected_houses: float | None = None
    affected_people: float | None = None
    affected_people_pct: float | None = None

    hazard_pct: float | None = None
    vulnerability_pct: float | None = None
    risk_pct: float | None = None

    # NEAP classification. How bad the hazard is *given the warning time* —
    # the same wind scores 16 with no notice and 8 with five days'. Echoed on
    # every row so a downloaded table carries the lead time it was read at.
    lead_time_hours: int | None = None
    neap_wind: int | None = None
    neap_surge: int | None = None
    neap_rain: int | None = None


class ResultPage(BaseModel):
    items: list[ResultRow]
    total: int
    page: int
    size: int
    level: AdminLevel
    metric: str
    #: the lead time the NEAP columns on these rows were classified at
    lead_time_hours: int | None = None
    #: min/max of the selected metric across the filtered set — drives the map legend
    metric_min: float | None = None
    metric_max: float | None = None


class MapResponse(BaseModel):
    """GeoJSON FeatureCollection, ready to hand to Leaflet."""

    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[dict[str, Any]]
    #: which administrative level the polygons are
    level: AdminLevel = "union"
    metric: str
    metric_label: str
    metric_unit: str
    metric_min: float | None = None
    metric_max: float | None = None
    feature_count: int = 0


class TrackResponse(BaseModel):
    """The cyclone's track line. Empty when the cyclone was imported without one."""

    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[dict[str, Any]]
    feature_count: int = 0


class BoundaryResponse(BaseModel):
    """District or division outlines, as GeoJSON lines, for the map overlay."""

    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[dict[str, Any]]
    level: str
    feature_count: int = 0


class RunSummary(BaseModel):
    """One model execution, as the run list and the status poll return it."""

    id: int
    cyclone_code: str
    #: "queued" | "running" | "succeeded" | "failed"
    status: str
    cyclone_id: int | None = None
    cyclone_name: str | None = None
    row_count: int | None = None
    #: Present only on a failed run — the model's own message, verbatim.
    error: str | None = None
    took_ms: int | None = None
    created_at: datetime
    finished_at: datetime | None = None


class RunAccepted(BaseModel):
    """The answer to starting a run: the work has begun, poll this id."""

    id: int
    cyclone_code: str
    status: str = "queued"
