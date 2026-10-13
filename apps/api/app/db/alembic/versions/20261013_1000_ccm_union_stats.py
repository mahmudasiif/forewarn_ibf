"""Per-union affected-people distribution, for the return-period trigger.

The CCM package carries, for every union, the mean and standard deviation of
the natural log of the number of people affected across its historical cyclone
record (Base_info/StructureDamageData.xlsx, sheet Coastal_Housing_info, columns
Avg and Std). The desktop tool joins them on the fly to answer "show me the
unions where this cyclone is worse than their 1-in-T-year event":

    zt = ((1 - 1/T)**0.135 - (1/T)**0.135) / 0.1975     # Gumbel reduced variate
    expected = exp(Avg + zt * Std)

They belong on ccm.unions rather than ccm.results: they describe the place, not
the cyclone, and putting them there lets the filter run in SQL instead of
pulling 1,585 rows into the API to compare them.

Revision ID: 0008_ccm_union_stats
Revises: 0007_merge_dfrm_ccm
"""
import sqlalchemy as sa
from alembic import op

revision = "0008_ccm_union_stats"
down_revision = "0007_merge_dfrm_ccm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "unions",
        sa.Column(
            "ln_affected_avg",
            sa.Float(),
            nullable=True,
            comment="Mean of ln(affected people) over the union's historical record.",
        ),
        schema="ccm",
    )
    op.add_column(
        "unions",
        sa.Column(
            "ln_affected_std",
            sa.Float(),
            nullable=True,
            comment="Standard deviation of ln(affected people) for the same record.",
        ),
        schema="ccm",
    )


def downgrade() -> None:
    op.drop_column("unions", "ln_affected_std", schema="ccm")
    op.drop_column("unions", "ln_affected_avg", schema="ccm")
