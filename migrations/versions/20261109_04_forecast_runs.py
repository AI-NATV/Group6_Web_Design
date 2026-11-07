"""Save forecast runs so owners can review earlier results.

Revision ID: 20261109_04
Revises: 20261108_03
"""

from alembic import op
import sqlalchemy as sa


revision = "20261109_04"
down_revision = "20261108_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "forecastrun",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("dataset_id", sa.Integer(), nullable=False),
        sa.Column("time_column", sa.String(length=200), nullable=False),
        sa.Column("target_column", sa.String(length=200), nullable=False),
        sa.Column("horizon", sa.Integer(), nullable=False),
        sa.Column("selected_model", sa.String(length=40), nullable=False),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dataset_id"], ["dataset.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_forecastrun_owner_id"), "forecastrun", ["owner_id"], unique=False)
    op.create_index(op.f("ix_forecastrun_dataset_id"), "forecastrun", ["dataset_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_forecastrun_dataset_id"), table_name="forecastrun")
    op.drop_index(op.f("ix_forecastrun_owner_id"), table_name="forecastrun")
    op.drop_table("forecastrun")
