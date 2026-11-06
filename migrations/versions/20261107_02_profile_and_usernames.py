"""Add optional profile fields and lower-case existing usernames.

Revision ID: 20261107_02
Revises: 20261103_01
"""

from alembic import op
import sqlalchemy as sa


revision = "20261107_02"
down_revision = "20261103_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user", sa.Column("display_name", sa.String(length=60), nullable=True))
    op.add_column("user", sa.Column("phone", sa.String(length=20), nullable=True))
    op.add_column("user", sa.Column("avatar", sa.Text(), nullable=True))

    # Usernames are compared in lower case. Accounts created before that rule may still
    # contain capitals, so lower-case them, but stop if two accounts would then collide.
    bind = op.get_bind()
    duplicates = bind.execute(sa.text(
        'SELECT lower(username) FROM "user" GROUP BY lower(username) HAVING count(*) > 1'
    )).fetchall()
    if duplicates:
        names = ", ".join(row[0] for row in duplicates)
        raise RuntimeError(
            f"Cannot lower-case usernames: these names exist in several letter cases: {names}. "
            "Rename or remove the duplicate accounts first."
        )
    bind.execute(sa.text('UPDATE "user" SET username = lower(username)'))


def downgrade() -> None:
    op.drop_column("user", "avatar")
    op.drop_column("user", "phone")
    op.drop_column("user", "display_name")
