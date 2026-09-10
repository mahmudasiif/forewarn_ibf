"""Widen the CCM damage-condition columns

The condition columns are not a simple Yes/No. The shipped data uses three
values, the longest being 'No polder in the area' (21 chars), which means there
is no polder infrastructure in that union at all — meaningfully different from
'No', which means a polder is present and was not damaged.

Revision ID: 0002_widen_conditions
Revises: 0001_ccm_schema
Create Date: 2026-09-09
"""
import sqlalchemy as sa
from alembic import op

revision = "0002_widen_conditions"
down_revision = "0001_ccm_schema"
branch_labels = None
depends_on = None

COLUMNS = ("polder_damage", "structure_damage", "agri_land_damage")


def upgrade() -> None:
    for column in COLUMNS:
        op.alter_column(
            "results",
            column,
            existing_type=sa.String(10),
            type_=sa.String(40),
            existing_nullable=True,
            schema="ccm",
        )


def downgrade() -> None:
    for column in COLUMNS:
        op.alter_column(
            "results",
            column,
            existing_type=sa.String(40),
            type_=sa.String(10),
            existing_nullable=True,
            schema="ccm",
        )
