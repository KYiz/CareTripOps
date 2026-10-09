"""Persist destination scope and visual preference metadata.

Revision ID: 0002_destination_media
Revises: 0001_initial
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0002_destination_media"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("requirements")}
    if "destination_scope" not in existing:
        op.add_column("requirements", sa.Column("destination_scope", sa.String(20), nullable=False, server_default="UNKNOWN"))
    if "attractions" not in existing:
        op.add_column("requirements", sa.Column("attractions", JSONB(), nullable=False, server_default="[]"))
    if "travel_pace" not in existing:
        op.add_column("requirements", sa.Column("travel_pace", sa.String(20), nullable=False, server_default="STANDARD"))
    op.execute("UPDATE requirements SET destination_scope = 'SUPPORTED' WHERE destination IN "
               "('Auckland', 'Queenstown', 'Rotorua', 'Wellington', 'Christchurch', 'Taupō')")
    op.alter_column("requirements", "destination_scope", server_default=None)
    op.alter_column("requirements", "attractions", server_default=None)
    op.alter_column("requirements", "travel_pace", server_default=None)


def downgrade() -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("requirements")}
    for column in ("travel_pace", "attractions", "destination_scope"):
        if column in existing:
            op.drop_column("requirements", column)
