"""Trip companion: deduplicated reminders and help requests.

Revision ID: 0011_trip_companion
Revises: 0010_privacy_controls
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "0011_trip_companion"
down_revision = "0010_privacy_controls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One reminder per order, recipient and milestone, however often the worker looks.
    op.add_column("notifications", sa.Column("dedupe_key", sa.String(160)))
    op.create_unique_constraint("uq_notifications_dedupe_key", "notifications", ["dedupe_key"])
    op.create_table(
        "help_requests",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("case_id", UUID(as_uuid=False), sa.ForeignKey("cases.id"), nullable=False, index=True),
        sa.Column("user_id", UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_by", UUID(as_uuid=False), sa.ForeignKey("users.id")),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("advisor_note", sa.Text),
    )


def downgrade() -> None:
    op.drop_table("help_requests")
    op.drop_constraint("uq_notifications_dedupe_key", "notifications", type_="unique")
    op.drop_column("notifications", "dedupe_key")
