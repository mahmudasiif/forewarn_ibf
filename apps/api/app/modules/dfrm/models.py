"""DFRM ORM models. Tables live in the `dfrm` schema.

* `runs` — the portal's audit record of one manual map/warning query (DFRM
  itself is stateless; the model service persists nothing).
* `forecast_sets` / `forecast_days` — the automated daily 5-day forecast,
  driven by the FFWC Bahadurabad feed (worker writes these; the API reads them).
"""
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

SCHEMA = "dfrm"


class DfrmRun(Base):
    """One DFRM query (a map or a warning) recorded for the audit trail."""

    __tablename__ = "runs"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    #: "map" | "warning"
    kind: Mapped[str] = mapped_column(String(10), index=True)
    #: District | Upazilla | Union | Village
    level: Mapped[str] = mapped_column(String(12))
    area_id: Mapped[str] = mapped_column(String(20))
    area_name: Mapped[str] = mapped_column(String(120))
    #: map layer (Inundation/Hazard/Risk/Vulnerability) or "Warning"
    layer: Mapped[str] = mapped_column(String(20))

    water_level: Mapped[float] = mapped_column(Float)
    #: "WL" (absolute) | "DL" (above danger level)
    wl_kind: Mapped[str] = mapped_column(String(4), default="WL")
    limb: Mapped[str] = mapped_column(String(24))
    #: free-text warning date (warnings only)
    date: Mapped[str | None] = mapped_column(String(20), nullable=True)

    river: Mapped[str] = mapped_column(String(20))
    station: Mapped[str] = mapped_column(String(60))
    return_period: Mapped[float | None] = mapped_column(Float, nullable=True)

    #: small result digest — feature_count/day for maps, selected risk for warnings
    summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class DfrmForecastSet(Base):
    """One automated daily run of the 5-day forecast (one per calendar day)."""

    __tablename__ = "forecast_sets"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    #: e.g. "FFWC/Bahadurabad"
    source: Mapped[str] = mapped_column(String(40))
    station: Mapped[str] = mapped_column(String(60))
    danger_level: Mapped[float] = mapped_column(Float)
    #: the observed level day 1 was anchored on
    observed_wl: Mapped[float | None] = mapped_column(Float, nullable=True)
    layer: Mapped[str] = mapped_column(String(20))
    level: Mapped[str] = mapped_column(String(12))
    #: when the FFWC data was pulled
    pulled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    days: Mapped[list["DfrmForecastDay"]] = relationship(
        back_populates="set", cascade="all, delete-orphan"
    )


class DfrmForecastDay(Base):
    """One forecast day for one target area (grain: set x day x area)."""

    __tablename__ = "forecast_days"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    set_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.forecast_sets.id", ondelete="CASCADE"), index=True
    )
    day_index: Mapped[int] = mapped_column(Integer)
    forecast_date: Mapped[date] = mapped_column(Date)
    water_level: Mapped[float] = mapped_column(Float)
    prev_water_level: Mapped[float | None] = mapped_column(Float, nullable=True)
    limb: Mapped[str] = mapped_column(String(24))
    phase: Mapped[str] = mapped_column(String(12))

    area_id: Mapped[str] = mapped_column(String(20))
    area_name: Mapped[str] = mapped_column(String(120))
    river: Mapped[str] = mapped_column(String(20))
    station: Mapped[str] = mapped_column(String(60))

    hydrograph_day: Mapped[str | None] = mapped_column(String(12), nullable=True)
    return_period: Mapped[float | None] = mapped_column(Float, nullable=True)
    feature_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metric_unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    metric_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    metric_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: MinIO key of the full /map response JSON (features + rivers + context)
    map_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="ok")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    set: Mapped["DfrmForecastSet"] = relationship(back_populates="days")
