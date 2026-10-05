"""CCM ORM models. Tables live in the `ccm` Postgres schema.

Four tables:
  unions   — the 1,585 union boundaries the model reports against (geometry)
  cyclones — one row per cyclone whose results have been loaded
  results  — one row per union per cyclone, holding the model's output metrics
  runs     — one row per model execution started from the portal
"""
from datetime import date, datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

SCHEMA = "ccm"


class CCMUnion(Base):
    """A union boundary. `union_geo` is the key CCM results join on."""

    __tablename__ = "unions"
    __table_args__ = (
        Index("ix_ccm_unions_district", "district"),
        Index("ix_ccm_unions_division", "division"),
        {"schema": SCHEMA},
    )

    union_geo: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    division: Mapped[str] = mapped_column(String(100))
    district: Mapped[str] = mapped_column(String(100))
    upazila: Mapped[str] = mapped_column(String(100))
    union_name: Mapped[str] = mapped_column(String(150))
    geom: Mapped[object] = mapped_column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Cyclone(Base):
    """A cyclone whose CCM results are loaded into the portal."""

    __tablename__ = "cyclones"
    __table_args__ = (
        UniqueConstraint("code", name="uq_ccm_cyclones_code"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    #: the CCM package's own identifier, e.g. "REMAL_Actual"
    code: Mapped[str] = mapped_column(String(120), index=True)
    #: display name, e.g. "Remal"
    name: Mapped[str] = mapped_column(String(120))
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    landfall_location: Mapped[str | None] = mapped_column(String(150), nullable=True)
    max_wind_speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    remark: Mapped[str | None] = mapped_column(String(200), nullable=True)
    #: "actual" for historical cyclones; "realtime" for runs produced later
    cyclone_type: Mapped[str] = mapped_column(String(30), default="actual")
    #: "package" (shipped with CCM v2.9.3) or "upload" (added through the portal)
    source: Mapped[str] = mapped_column(String(30), default="package")
    model_version: Mapped[str] = mapped_column(String(30), default="v2.9.3")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: The cyclone's track as a GeoJSON FeatureCollection. The CCM package
    #: ships one shapefile per cyclone and the desktop tool drew it over the
    #: map; storing it here lets the portal do the same without shipping
    #: shapefiles to the browser.
    track_geojson: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    results: Mapped[list["CCMResult"]] = relationship(
        back_populates="cyclone", cascade="all, delete-orphan"
    )


class CCMResult(Base):
    """One CCM output row: what this cyclone does to this union."""

    __tablename__ = "results"
    __table_args__ = (
        UniqueConstraint("cyclone_id", "union_geo", name="uq_ccm_results_cyclone_union"),
        Index("ix_ccm_results_cyclone", "cyclone_id"),
        Index("ix_ccm_results_risk", "cyclone_id", "risk_pct"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cyclone_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.cyclones.id", ondelete="CASCADE")
    )
    union_geo: Mapped[int] = mapped_column(BigInteger, index=True)

    # Administrative labels are denormalised from the CSV so results can be read
    # and exported without a join, and so a result survives a boundary revision.
    division: Mapped[str] = mapped_column(String(100))
    district: Mapped[str] = mapped_column(String(100))
    upazila: Mapped[str] = mapped_column(String(100))
    union_name: Mapped[str] = mapped_column(String(150))

    # Hazard intensity
    surge_height_m: Mapped[float | None] = mapped_column(Float)
    wind_speed_kmh: Mapped[float | None] = mapped_column(Float)
    thrust_force: Mapped[float | None] = mapped_column(Float)
    rainfall_72h_mm: Mapped[float | None] = mapped_column(Float)

    # Damage conditions. Not a simple Yes/No: the shipped data also uses
    # 'No polder in the area', meaning no polder infrastructure exists there —
    # which is different from 'No', meaning a polder is present and undamaged.
    polder_damage: Mapped[str | None] = mapped_column(String(40))
    structure_damage: Mapped[str | None] = mapped_column(String(40))
    agri_land_damage: Mapped[str | None] = mapped_column(String(40))

    # Impact
    flooded_area_km2: Mapped[float | None] = mapped_column(Float)
    flooded_area_pct: Mapped[float | None] = mapped_column(Float)
    house_damage_million_bdt: Mapped[float | None] = mapped_column(Float)
    affected_houses: Mapped[float | None] = mapped_column(Float)
    affected_people: Mapped[float | None] = mapped_column(Float)
    affected_people_pct: Mapped[float | None] = mapped_column(Float)

    # Risk composition
    hazard_pct: Mapped[float | None] = mapped_column(Float)
    vulnerability_pct: Mapped[float | None] = mapped_column(Float)
    risk_pct: Mapped[float | None] = mapped_column(Float)

    cyclone: Mapped["Cyclone"] = relationship(back_populates="results")


class CCMRun(Base):
    """One execution of the model, started by an operator through the portal.

    A run takes minutes, so it is recorded before the work starts and updated
    as it progresses — the browser polls this row rather than holding a
    request open, and a closed tab or a page refresh does not lose the run.
    """

    __tablename__ = "runs"
    __table_args__ = (
        Index("ix_ccm_runs_status", "status"),
        Index("ix_ccm_runs_created_at", "created_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    #: The code the results are stored under, e.g. "MD19072026_Actual".
    cyclone_code: Mapped[str] = mapped_column(String(120), index=True)
    #: "queued" | "running" | "succeeded" | "failed"
    status: Mapped[str] = mapped_column(String(20), default="queued")
    #: Populated once the results land, so the UI can link straight to them.
    cyclone_id: Mapped[int | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.cyclones.id", ondelete="SET NULL"), nullable=True
    )
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Which files were uploaded, and the metadata entered with them — kept so
    #: a run can be explained (or re-run) later without the originals.
    inputs: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    #: Why a failed run failed, verbatim, for the operator to act on.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    took_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
