"""Persist date selections with saved dashboard visuals.

Revision ID: 20261110_06
Revises: 20261109_05
"""

from alembic import op
import sqlalchemy as sa


revision = "20261110_06"
down_revision = "20261109_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("visual")}
    if "date_filter" not in columns:
        op.add_column("visual", sa.Column("date_filter", sa.JSON(), nullable=True))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("visual")}
    if "date_filter" in columns:
        op.drop_column("visual", "date_filter")
