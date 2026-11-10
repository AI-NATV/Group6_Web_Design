"""Store messages submitted from the public landing page.

Revision ID: 20261109_05
Revises: 20261109_04
"""

from alembic import op
import sqlalchemy as sa


revision = "20261109_05"
down_revision = "20261109_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "feedback" not in inspector.get_table_names():
        op.create_table(
            "feedback",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("full_name", sa.String(length=100), nullable=False),
            sa.Column("email", sa.String(length=254), nullable=False),
            sa.Column("message", sa.String(length=2000), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("feedback")}
    if op.f("ix_feedback_created_at") not in indexes:
        op.create_index(op.f("ix_feedback_created_at"), "feedback", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_feedback_created_at"), table_name="feedback")
    op.drop_table("feedback")
