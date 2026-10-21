"""Step-up confirmation, terms consent, the consented traveler profile and account deletion.

Revision ID: 0010_privacy_controls
Revises: 0009_booking_lifecycle
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "0010_privacy_controls"
down_revision = "0009_booking_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("login_codes", sa.Column("purpose", sa.String(10), nullable=False, server_default="login"))
    op.add_column("user_sessions", sa.Column("reauthenticated_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("terms_version", sa.String(20)))
    op.add_column("users", sa.Column("terms_accepted_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("sensitive_consent_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.create_table(
        "traveler_profiles",
        sa.Column("user_id", UUID(as_uuid=False), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("needs", JSONB, nullable=False, server_default="{}"),
        sa.Column("emergency_contact", JSONB, nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    # Sessions opened before this migration count as freshly signed in until they next sign in.
    op.execute("UPDATE user_sessions SET reauthenticated_at = created_at")


def downgrade() -> None:
    op.drop_table("traveler_profiles")
    for column in ("deleted_at", "sensitive_consent_at", "terms_accepted_at", "terms_version"):
        op.drop_column("users", column)
    op.drop_column("user_sessions", "reauthenticated_at")
    op.drop_column("login_codes", "purpose")
