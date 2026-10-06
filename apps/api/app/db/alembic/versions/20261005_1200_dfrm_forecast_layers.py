"""DFRM forecast — per-layer rows (Inundation/Hazard/Risk/Vulnerability)

Revision ID: 0006_dfrm_forecast_layers
Revises: 0005_dfrm_forecast
Create Date: 2026-10-05

The automated 5-day forecast now generates all four map layers per day+area, so
forecast_days gains a `layer` column and the uniqueness key widens to include it.
"""
import sqlalchemy as sa
from alembic import op

revision = "0006_dfrm_forecast_layers"
down_revision = "0005_dfrm_forecast"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "forecast_days",
        sa.Column("layer", sa.String(20), nullable=False, server_default="Inundation"),
        schema="dfrm",
    )
    op.drop_constraint("uq_forecast_day_area", "forecast_days", schema="dfrm", type_="unique")
    op.create_unique_constraint(
        "uq_forecast_day_area_layer",
        "forecast_days",
        ["set_id", "day_index", "area_id", "layer"],
        schema="dfrm",
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_forecast_day_area_layer", "forecast_days", schema="dfrm", type_="unique"
    )
    op.create_unique_constraint(
        "uq_forecast_day_area",
        "forecast_days",
        ["set_id", "day_index", "area_id"],
        schema="dfrm",
    )
    op.drop_column("forecast_days", "layer", schema="dfrm")
