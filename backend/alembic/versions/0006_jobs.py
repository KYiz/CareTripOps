"""Durable workflow job queue and change notifications for live updates.

Revision ID: 0006_jobs
Revises: 0005_accounts
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "0006_jobs"
down_revision = "0005_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("case_id", UUID(as_uuid=False), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(80)),
        sa.Column("last_error", sa.String(200)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.execute("CREATE UNIQUE INDEX uq_active_job_per_case ON jobs (case_id) WHERE status IN ('QUEUED', 'RUNNING')")
    op.execute("CREATE INDEX ix_jobs_queued ON jobs (id) WHERE status = 'QUEUED'")
    # Every Case state change writes an audit event, and every run changes a job row. Notifying on both
    # lets the API push "something changed" to browsers instead of being polled.
    op.execute("""
    CREATE OR REPLACE FUNCTION notify_case_change() RETURNS trigger AS $$
    BEGIN
      PERFORM pg_notify('case_events', NEW.case_id::text);
      RETURN NULL;
    END; $$ LANGUAGE plpgsql
    """)
    op.execute("CREATE TRIGGER audit_event_notify AFTER INSERT ON audit_events "
               "FOR EACH ROW EXECUTE FUNCTION notify_case_change()")
    op.execute("CREATE TRIGGER job_notify AFTER INSERT OR UPDATE OF status ON jobs "
               "FOR EACH ROW EXECUTE FUNCTION notify_case_change()")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS job_notify ON jobs")
    op.execute("DROP TRIGGER IF EXISTS audit_event_notify ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS notify_case_change()")
    op.drop_table("jobs")
