"""Persist the selected attraction and illustrative revision proposals.

Revision ID: 0003_guide_state
Revises: 0002_destination_media
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0003_guide_state"
down_revision = "0002_destination_media"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("cases")}
    if "guide_state" not in columns:
        op.add_column("cases", sa.Column("guide_state", JSONB(), nullable=False, server_default="{}"))
        op.alter_column("cases", "guide_state", server_default=None)


def downgrade() -> None:
    op.drop_column("cases", "guide_state")
