"""DFRM ORM models. Tables live in the `dfrm` schema.

One table: `runs`. DFRM itself is stateless — the model service persists
nothing — so each row here is the portal's own audit record of one map or
warning query an operator ran (the "run" concept the other models have).
"""
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

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
