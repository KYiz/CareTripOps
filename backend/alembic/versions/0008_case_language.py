"""Record the language a Case was planned in.

Revision ID: 0008_case_language
Revises: 0007_split_guide_state
"""
from alembic import op
import sqlalchemy as sa


revision = "0008_case_language"
down_revision = "0007_split_guide_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("language", sa.String(5), nullable=False, server_default="en"))
    op.alter_column("cases", "language", server_default=None)


def downgrade() -> None:
    op.drop_column("cases", "language")
