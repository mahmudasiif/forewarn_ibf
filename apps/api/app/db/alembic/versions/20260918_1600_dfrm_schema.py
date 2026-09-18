"""DFRM schema — runs (query audit trail)

Revision ID: 0004_dfrm_schema
Revises: 0003_preparedness_schema
Create Date: 2026-09-18
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_dfrm_schema"
down_revision = "0003_preparedness_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS dfrm")

    op.create_table(
        "runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("level", sa.String(12), nullable=False),
        sa.Column("area_id", sa.String(20), nullable=False),
        sa.Column("area_name", sa.String(120), nullable=False),
        sa.Column("layer", sa.String(20), nullable=False),
        sa.Column("water_level", sa.Float(), nullable=False),
        sa.Column("wl_kind", sa.String(4), server_default="WL", nullable=False),
        sa.Column("limb", sa.String(24), nullable=False),
        sa.Column("date", sa.String(20), nullable=True),
        sa.Column("river", sa.String(20), nullable=False),
        sa.Column("station", sa.String(60), nullable=False),
        sa.Column("return_period", sa.Float(), nullable=True),
        sa.Column("summary", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="dfrm",
    )
    op.create_index("ix_dfrm_runs_kind", "runs", ["kind"], schema="dfrm")
    op.create_index("ix_dfrm_runs_created_at", "runs", ["created_at"], schema="dfrm")


def downgrade() -> None:
    op.drop_index("ix_dfrm_runs_created_at", table_name="runs", schema="dfrm")
    op.drop_index("ix_dfrm_runs_kind", table_name="runs", schema="dfrm")
    op.drop_table("runs", schema="dfrm")
    op.execute("DROP SCHEMA IF EXISTS dfrm")
