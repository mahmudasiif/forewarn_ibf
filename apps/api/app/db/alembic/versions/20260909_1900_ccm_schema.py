"""CCM schema — unions, cyclones and results

Revision ID: 0001_ccm_schema
Revises:
Create Date: 2026-09-09
"""
import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision = "0001_ccm_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS ccm")

    op.create_table(
        "unions",
        sa.Column("union_geo", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("division", sa.String(100), nullable=False),
        sa.Column("district", sa.String(100), nullable=False),
        sa.Column("upazila", sa.String(100), nullable=False),
        sa.Column("union_name", sa.String(150), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON", srid=4326, spatial_index=True
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="ccm",
    )
    op.create_index("ix_ccm_unions_district", "unions", ["district"], schema="ccm")
    op.create_index("ix_ccm_unions_division", "unions", ["division"], schema="ccm")

    op.create_table(
        "cyclones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(120), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("landfall_location", sa.String(150), nullable=True),
        sa.Column("max_wind_speed", sa.Float(), nullable=True),
        sa.Column("remark", sa.String(200), nullable=True),
        sa.Column("cyclone_type", sa.String(30), server_default="actual", nullable=False),
        sa.Column("source", sa.String(30), server_default="package", nullable=False),
        sa.Column("model_version", sa.String(30), server_default="v2.9.3", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("code", name="uq_ccm_cyclones_code"),
        schema="ccm",
    )
    op.create_index("ix_ccm_cyclones_code", "cyclones", ["code"], schema="ccm")

    metric_columns = [
        "surge_height_m",
        "wind_speed_kmh",
        "thrust_force",
        "rainfall_72h_mm",
        "flooded_area_km2",
        "flooded_area_pct",
        "house_damage_million_bdt",
        "affected_houses",
        "affected_people",
        "affected_people_pct",
        "hazard_pct",
        "vulnerability_pct",
        "risk_pct",
    ]

    op.create_table(
        "results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "cyclone_id",
            sa.Integer(),
            sa.ForeignKey("ccm.cyclones.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("union_geo", sa.BigInteger(), nullable=False),
        sa.Column("division", sa.String(100), nullable=False),
        sa.Column("district", sa.String(100), nullable=False),
        sa.Column("upazila", sa.String(100), nullable=False),
        sa.Column("union_name", sa.String(150), nullable=False),
        sa.Column("polder_damage", sa.String(10)),
        sa.Column("structure_damage", sa.String(10)),
        sa.Column("agri_land_damage", sa.String(10)),
        *[sa.Column(name, sa.Float()) for name in metric_columns],
        sa.UniqueConstraint("cyclone_id", "union_geo", name="uq_ccm_results_cyclone_union"),
        schema="ccm",
    )
    op.create_index("ix_ccm_results_cyclone", "results", ["cyclone_id"], schema="ccm")
    op.create_index("ix_ccm_results_union_geo", "results", ["union_geo"], schema="ccm")
    op.create_index("ix_ccm_results_risk", "results", ["cyclone_id", "risk_pct"], schema="ccm")


def downgrade() -> None:
    op.drop_table("results", schema="ccm")
    op.drop_table("cyclones", schema="ccm")
    op.drop_table("unions", schema="ccm")
