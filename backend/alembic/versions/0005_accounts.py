"""Traveler accounts, email login codes, sessions, and family members per Case.

Replaces the per-Case browser token. Cases created before this revision have no owner and
are no longer reachable from the browser.

Revision ID: 0005_accounts
Revises: 0004_case_access
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "0005_accounts"
down_revision = "0004_case_access"
branch_labels = None
depends_on = None


def _ts(name: str, nullable: bool = False):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("display_name", sa.String(80)),
        _ts("created_at"), _ts("last_login_at", nullable=True),
    )
    op.create_table(
        "login_codes",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        _ts("expires_at"), _ts("consumed_at", nullable=True), _ts("created_at"),
    )
    op.create_index("ix_login_codes_email", "login_codes", ["email"])
    op.create_table(
        "user_sessions",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        _ts("created_at"), _ts("last_seen_at"), _ts("expires_at"), _ts("revoked_at", nullable=True),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_table(
        "case_members",
        sa.Column("case_id", UUID(as_uuid=False), sa.ForeignKey("cases.id"), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=False), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("role", sa.String(20), nullable=False),
        _ts("created_at"),
    )
    op.create_index("ix_case_members_user_id", "case_members", ["user_id"])
    op.create_table(
        "case_invitations",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("case_id", UUID(as_uuid=False), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("invited_by", UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        _ts("created_at"), _ts("expires_at"), _ts("accepted_at", nullable=True), _ts("revoked_at", nullable=True),
    )
    op.create_index("ix_case_invitations_email", "case_invitations", ["email"])
    op.execute("CREATE UNIQUE INDEX uq_open_invitation ON case_invitations (case_id, email) "
               "WHERE accepted_at IS NULL AND revoked_at IS NULL")
    op.drop_column("cases", "access_token_hash")


def downgrade() -> None:
    op.add_column("cases", sa.Column("access_token_hash", sa.String(64), nullable=True))
    for table in ("case_invitations", "case_members", "user_sessions", "login_codes", "users"):
        op.drop_table(table)
