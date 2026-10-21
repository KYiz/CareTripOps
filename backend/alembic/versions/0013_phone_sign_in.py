"""Sign-in by text message for accounts that verified a mobile number.

Revision ID: 0013_phone_sign_in
Revises: 0012_case_notes
"""
from alembic import op
import sqlalchemy as sa


revision = "0013_phone_sign_in"
down_revision = "0012_case_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A code is sent to an email address or to "tel:+64...".
    op.alter_column("login_codes", "email", new_column_name="identifier")
    op.execute("ALTER INDEX ix_login_codes_email RENAME TO ix_login_codes_identifier")
    op.add_column("users", sa.Column("phone", sa.String(20)))
    op.add_column("users", sa.Column("phone_verified_at", sa.DateTime(timezone=True)))
    op.create_unique_constraint("uq_users_phone", "users", ["phone"])


def downgrade() -> None:
    op.drop_constraint("uq_users_phone", "users", type_="unique")
    op.drop_column("users", "phone_verified_at")
    op.drop_column("users", "phone")
    op.execute("DELETE FROM login_codes WHERE identifier LIKE 'tel:%'")
    op.execute("ALTER INDEX ix_login_codes_identifier RENAME TO ix_login_codes_email")
    op.alter_column("login_codes", "identifier", new_column_name="email")
