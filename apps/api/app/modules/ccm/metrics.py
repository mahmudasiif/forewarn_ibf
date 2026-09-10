"""
The CCM result metrics, defined once and served to the frontend.

These mirror the columns of the CCM result tables produced by CCM v2.9.3.
The frontend's "Map Type" and "Trigger Parameter" dropdowns are built from
this registry, so a new metric only ever has to be added here.
"""
from dataclasses import dataclass, asdict
from typing import Literal

Aggregation = Literal["sum", "max", "mean"]


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    unit: str
    #: how to roll this metric up when viewing at upazila/district/division level
    aggregation: Aggregation
    #: metrics suitable for colouring the map / triggering on
    mappable: bool = True
    description: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


METRICS: tuple[Metric, ...] = (
    Metric("risk_pct", "Risk", "%", "mean", description="Combined hazard and vulnerability"),
    Metric("hazard_pct", "Hazard", "%", "mean"),
    Metric("vulnerability_pct", "Vulnerability", "%", "mean"),
    Metric("surge_height_m", "Surge Height", "m", "max"),
    Metric("wind_speed_kmh", "Wind Speed", "km/hr", "max"),
    Metric("rainfall_72h_mm", "72hr Cumulative Rainfall", "mm", "mean"),
    Metric("thrust_force", "Thrust Force", "", "max"),
    Metric("flooded_area_km2", "Flooded Area", "km²", "sum"),
    Metric("flooded_area_pct", "Flooded Area", "%", "mean"),
    Metric("affected_people", "Affected People", "people", "sum"),
    Metric("affected_people_pct", "Affected People", "%", "mean"),
    Metric("affected_houses", "Affected Houses", "houses", "sum"),
    Metric("house_damage_million_bdt", "House Damage", "million BDT", "sum"),
)

METRICS_BY_KEY: dict[str, Metric] = {m.key: m for m in METRICS}

#: Yes/No condition columns — shown in the table, not used for colouring
CONDITION_FIELDS: tuple[tuple[str, str], ...] = (
    ("polder_damage", "Polder Damage"),
    ("structure_damage", "Structure Damage"),
    ("agri_land_damage", "Agricultural Land Damage"),
)

DEFAULT_METRIC = "risk_pct"


def resolve(key: str | None) -> Metric:
    """Return a known metric, falling back to the default."""
    return METRICS_BY_KEY.get(key or "", METRICS_BY_KEY[DEFAULT_METRIC])
