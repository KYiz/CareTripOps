"""Add per-case demo access capabilities.

Revision ID: 0004_case_access
Revises: 0003_guide_state
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_case_access"
down_revision = "0003_guide_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("cases")}
    if "access_token_hash" not in columns:
        op.add_column("cases", sa.Column("access_token_hash", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("cases", "access_token_hash")
