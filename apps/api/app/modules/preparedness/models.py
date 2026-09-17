"""Preparedness Guidance ORM models. Tables live in the `preparedness` schema.

One table: `runs`. Each row is one execution of the impact + guidance pipeline
against an uploaded forecast. Heavy artifacts (maps, spreadsheets) live in object
storage; the row keeps their keys plus the summary stats and guideline text.
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

SCHEMA = "preparedness"


class Run(Base):
    """One preparedness-guidance run."""

    __tablename__ = "runs"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    cyclone_name: Mapped[str] = mapped_column(String(120))
    #: queued | running | succeeded | failed
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    #: internal damage-curve model of the pipeline: "ccm" or "safir"
    damage_model: Mapped[str] = mapped_column(String(20), default="ccm")
    #: whether LLM polish was requested (honoured only when a key is configured)
    polished: Mapped[bool] = mapped_column(default=True)
    #: whether polish actually ran (a key was present)
    llm_polished: Mapped[bool] = mapped_column(default=False)

    #: {"wind": {"filename","key"}, "rainfall": {...}?, "storm_surge": {...}?}
    input_files: Mapped[dict] = mapped_column(JSONB, default=dict)

    #: manifest summary + track/extreme records, for the stat tiles
    summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    guideline_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: [{"label","name","key","content_type","size"}]
    artifacts: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
