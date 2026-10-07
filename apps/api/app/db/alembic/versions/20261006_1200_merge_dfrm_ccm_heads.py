"""merge dfrm-forecast + ccm-runs branches into a single head

Revision ID: 0007_merge_dfrm_ccm
Revises: 0006_dfrm_forecast_layers, 0005_ccm_runs
Create Date: 2026-10-06

Two migrations were authored concurrently off 0004_dfrm_schema — the DFRM
forecast branch (0005_dfrm_forecast -> 0006_dfrm_forecast_layers) and the CCM
runs branch (0005_ccm_runs). This empty merge revision joins them so there is a
single head and `alembic upgrade head` works again.
"""

revision = "0007_merge_dfrm_ccm"
down_revision = ("0006_dfrm_forecast_layers", "0005_ccm_runs")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
