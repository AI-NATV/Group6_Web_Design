"""Create the initial user, dataset and visual tables.

Revision ID: 20261103_01
Revises: None
"""

from alembic import op
import sqlalchemy as sa


revision = "20261103_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=30), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("role", sa.String(length=5), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_username"), "user", ["username"], unique=True)

    op.create_table(
        "dataset",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("rows", sa.Integer(), nullable=False),
        sa.Column("columns", sa.JSON(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("profiles", sa.JSON(), nullable=False),
        sa.Column("semantic_model", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_dataset_owner_id"), "dataset", ["owner_id"], unique=False)

    op.create_table(
        "visual",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dataset_id", sa.Integer(), nullable=False),
        sa.Column("chart_type", sa.String(length=7), nullable=False),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("aggregation", sa.String(length=7), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["dataset.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_visual_dataset_id"), "visual", ["dataset_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_visual_dataset_id"), table_name="visual")
    op.drop_table("visual")
    op.drop_index(op.f("ix_dataset_owner_id"), table_name="dataset")
    op.drop_table("dataset")
    op.drop_index(op.f("ix_user_username"), table_name="user")
    op.drop_table("user")
