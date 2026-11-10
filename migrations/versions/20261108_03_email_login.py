"""Use the email address as the sign-in name (replaces user.username).

Revision ID: 20261108_03
Revises: 20261107_02
"""

from alembic import op
import sqlalchemy as sa


revision = "20261108_03"
down_revision = "20261107_02"
branch_labels = None
depends_on = None

EMAIL_LIKE = "%_@_%.__%"


def upgrade() -> None:
    bind = op.get_bind()
    # Existing usernames are not email addresses. Stop with a clear list instead of
    # guessing an address for anyone; fix or remove those accounts, then run again.
    invalid = bind.execute(sa.text(
        'SELECT username FROM "user" WHERE username NOT LIKE :pattern'
    ), {"pattern": EMAIL_LIKE}).fetchall()
    if invalid:
        names = ", ".join(row[0] for row in invalid)
        raise RuntimeError(
            f"These accounts do not have an email address and cannot sign in after this change: {names}. "
            "Change each username to an email address (or delete the account) and run the migration again."
        )
    duplicates = bind.execute(sa.text(
        'SELECT lower(username) FROM "user" GROUP BY lower(username) HAVING count(*) > 1'
    )).fetchall()
    if duplicates:
        names = ", ".join(row[0] for row in duplicates)
        raise RuntimeError(f"These email addresses belong to more than one account: {names}.")

    op.drop_index(op.f("ix_user_username"), table_name="user")
    op.execute('ALTER TABLE "user" RENAME COLUMN username TO email')
    bind.execute(sa.text('UPDATE "user" SET email = lower(trim(email))'))
    op.create_index(op.f("ix_user_email"), "user", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_email"), table_name="user")
    op.execute('ALTER TABLE "user" RENAME COLUMN email TO username')
    op.create_index(op.f("ix_user_username"), "user", ["username"], unique=True)
