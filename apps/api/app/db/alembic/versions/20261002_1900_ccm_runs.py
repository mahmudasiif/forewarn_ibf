"""CCM runs — model executions started from the portal, plus cyclone tracks

Adds:
  ccm.runs                 one row per model execution (status, inputs, error)
  ccm.cyclones.track_geojson   the cyclone's track, for drawing on the map

Revision ID: 0005_ccm_runs
Revises: 0004_dfrm_schema
Create Date: 2026-10-02
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_ccm_runs"
down_revision = "0004_dfrm_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cyclones",
        sa.Column("track_geojson", postgresql.JSONB(), nullable=True),
        schema="ccm",
    )

    op.create_table(
        "runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cyclone_code", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), server_default="queued", nullable=False),
        sa.Column(
            "cyclone_id",
            sa.Integer(),
            sa.ForeignKey("ccm.cyclones.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("inputs", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("took_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        schema="ccm",
    )
    op.create_index("ix_ccm_runs_cyclone_code", "runs", ["cyclone_code"], schema="ccm")
    op.create_index("ix_ccm_runs_status", "runs", ["status"], schema="ccm")
    op.create_index("ix_ccm_runs_created_at", "runs", ["created_at"], schema="ccm")


def downgrade() -> None:
    op.drop_index("ix_ccm_runs_created_at", table_name="runs", schema="ccm")
    op.drop_index("ix_ccm_runs_status", table_name="runs", schema="ccm")
    op.drop_index("ix_ccm_runs_cyclone_code", table_name="runs", schema="ccm")
    op.drop_table("runs", schema="ccm")
    op.drop_column("cyclones", "track_geojson", schema="ccm")
