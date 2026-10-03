"""DFRM forecast — automated 5-day FFWC-driven forecast sets

Revision ID: 0005_dfrm_forecast
Revises: 0004_dfrm_schema
Create Date: 2026-09-28

Two tables in the existing `dfrm` schema:
  * forecast_sets — one row per daily auto-run (keyed by run_date)
  * forecast_days — one row per (forecast day x target area) under a set
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_dfrm_forecast"
down_revision = "0004_dfrm_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "forecast_sets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_date", sa.Date(), nullable=False, unique=True),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("station", sa.String(60), nullable=False),
        sa.Column("danger_level", sa.Float(), nullable=False),
        sa.Column("observed_wl", sa.Float(), nullable=True),
        sa.Column("layer", sa.String(20), nullable=False),
        sa.Column("level", sa.String(12), nullable=False),
        sa.Column("pulled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="dfrm",
    )

    op.create_table(
        "forecast_days",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("set_id", sa.Integer(), nullable=False),
        sa.Column("day_index", sa.Integer(), nullable=False),
        sa.Column("forecast_date", sa.Date(), nullable=False),
        sa.Column("water_level", sa.Float(), nullable=False),
        sa.Column("prev_water_level", sa.Float(), nullable=True),
        sa.Column("limb", sa.String(24), nullable=False),
        sa.Column("phase", sa.String(12), nullable=False),
        sa.Column("area_id", sa.String(20), nullable=False),
        sa.Column("area_name", sa.String(120), nullable=False),
        sa.Column("river", sa.String(20), nullable=False),
        sa.Column("station", sa.String(60), nullable=False),
        sa.Column("hydrograph_day", sa.String(12), nullable=True),
        sa.Column("return_period", sa.Float(), nullable=True),
        sa.Column("feature_count", sa.Integer(), nullable=True),
        sa.Column("metric_unit", sa.String(20), nullable=True),
        sa.Column("metric_min", sa.Float(), nullable=True),
        sa.Column("metric_max", sa.Float(), nullable=True),
        sa.Column("map_key", sa.String(200), nullable=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="ok"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["set_id"], ["dfrm.forecast_sets.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("set_id", "day_index", "area_id", name="uq_forecast_day_area"),
        schema="dfrm",
    )
    op.create_index("ix_dfrm_forecast_days_set", "forecast_days", ["set_id"], schema="dfrm")


def downgrade() -> None:
    op.drop_index("ix_dfrm_forecast_days_set", table_name="forecast_days", schema="dfrm")
    op.drop_table("forecast_days", schema="dfrm")
    op.drop_table("forecast_sets", schema="dfrm")
