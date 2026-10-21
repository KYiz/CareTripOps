"""Advisor notes on a trip.

Revision ID: 0012_case_notes
Revises: 0011_trip_companion
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "0012_case_notes"
down_revision = "0011_trip_companion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_notes",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("case_id", UUID(as_uuid=False), sa.ForeignKey("cases.id"), nullable=False, index=True),
        sa.Column("author_id", UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("case_notes")
