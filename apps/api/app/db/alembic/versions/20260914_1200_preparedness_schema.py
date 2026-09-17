"""Preparedness Guidance schema — runs

Revision ID: 0003_preparedness_schema
Revises: 0002_widen_conditions
Create Date: 2026-09-14
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_preparedness_schema"
down_revision = "0002_widen_conditions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS preparedness")

    op.create_table(
        "runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cyclone_name", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), server_default="queued", nullable=False),
        sa.Column("damage_model", sa.String(20), server_default="ccm", nullable=False),
        sa.Column("polished", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("llm_polished", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("input_files", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("summary", postgresql.JSONB(), nullable=True),
        sa.Column("guideline_markdown", sa.Text(), nullable=True),
        sa.Column("artifacts", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        schema="preparedness",
    )
    op.create_index("ix_preparedness_runs_status", "runs", ["status"], schema="preparedness")


def downgrade() -> None:
    op.drop_index("ix_preparedness_runs_status", table_name="runs", schema="preparedness")
    op.drop_table("runs", schema="preparedness")
    op.execute("DROP SCHEMA IF EXISTS preparedness")
