"""Initial eight-table business schema.

Explicit DDL, independent of the current SQLAlchemy models, so a fresh database follows the same
path as an upgraded one. Columns added later belong to 0002-0004.

Revision ID: 0001_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def _id():
    return sa.Column("id", UUID(as_uuid=False), primary_key=True)


def _ts(name: str, nullable: bool = False):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade():
    op.create_table(
        "cases", _id(),
        sa.Column("thread_id", sa.String(36), nullable=False, unique=True),
        sa.Column("original_request", sa.Text(), nullable=False),
        sa.Column("demo_date", sa.Date()),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("active_node", sa.String(80), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("clarification_count", sa.Integer(), nullable=False),
        sa.Column("llm_calls", sa.Integer(), nullable=False),
        _ts("created_at"), _ts("updated_at"),
    )
    op.create_table(
        "requirements", _id(),
        sa.Column("case_id", UUID(as_uuid=False), sa.ForeignKey("cases.id"), nullable=False, unique=True),
        sa.Column("destination", sa.String(120)),
        sa.Column("departure_date", sa.Date()),
        sa.Column("traveler_count", sa.Integer()),
        sa.Column("duration_days", sa.Integer()),
        sa.Column("budget", sa.Numeric(12, 2)),
        sa.Column("currency", sa.String(3)),
        sa.Column("hard_constraints", JSONB(), nullable=False),
        sa.Column("missing_fields", JSONB(), nullable=False),
    )
    op.create_table(
        "offers", _id(),
        sa.Column("case_id", UUID(as_uuid=False), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("catalog_product_id", sa.String(40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("includes", JSONB(), nullable=False),
        sa.Column("supplier_claims", JSONB(), nullable=False),
        _ts("expires_at"), _ts("created_at"),
        sa.UniqueConstraint("case_id", "catalog_product_id", "version"),
    )
    op.create_table(
        "evidence", _id(),
        sa.Column("offer_id", UUID(as_uuid=False), sa.ForeignKey("offers.id"), nullable=False),
        sa.Column("claim_type", sa.String(80), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("polarity", sa.String(20), nullable=False),
        sa.Column("source_strength", sa.String(20), nullable=False),
        sa.Column("source_reference", sa.String(120), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        _ts("source_time"),
    )
    op.create_table(
        "offer_assessments", _id(),
        sa.Column("offer_id", UUID(as_uuid=False), sa.ForeignKey("offers.id"), nullable=False),
        sa.Column("claim_type", sa.String(80), nullable=False),
        sa.Column("verdict", sa.String(12), nullable=False),
        sa.Column("reason_code", sa.String(80), nullable=False),
        sa.Column("assessment_version", sa.Integer(), nullable=False),
        sa.Column("source_refs", JSONB(), nullable=False),
        _ts("assessed_at"),
        sa.UniqueConstraint("offer_id", "claim_type", "assessment_version"),
    )
    op.create_table(
        "approvals", _id(),
        sa.Column("case_id", UUID(as_uuid=False), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("offer_id", UUID(as_uuid=False), sa.ForeignKey("offers.id"), nullable=False),
        sa.Column("offer_version", sa.Integer(), nullable=False),
        sa.Column("approved_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("case_state_version", sa.Integer(), nullable=False),
        sa.Column("nonce_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        _ts("created_at"), _ts("decided_at", nullable=True),
    )
    op.create_table(
        "orders", _id(),
        sa.Column("case_id", UUID(as_uuid=False), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("offer_id", UUID(as_uuid=False), sa.ForeignKey("offers.id"), nullable=False),
        sa.Column("approval_id", UUID(as_uuid=False), sa.ForeignKey("approvals.id"), nullable=False, unique=True),
        sa.Column("idempotency_key", sa.String(120), nullable=False, unique=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        _ts("created_at"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("case_id", UUID(as_uuid=False), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("agent_name", sa.String(60), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        _ts("created_at"),
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_pending_approval_case ON approvals (case_id) WHERE status = 'PENDING'")
    op.execute("""
    CREATE OR REPLACE FUNCTION prevent_offer_snapshot_update() RETURNS trigger AS $$
    BEGIN
      IF ROW(OLD.case_id, OLD.catalog_product_id, OLD.version, OLD.total_amount,
             OLD.currency, OLD.includes, OLD.supplier_claims, OLD.expires_at)
         IS DISTINCT FROM
         ROW(NEW.case_id, NEW.catalog_product_id, NEW.version, NEW.total_amount,
             NEW.currency, NEW.includes, NEW.supplier_claims, NEW.expires_at) THEN
        RAISE EXCEPTION 'offer snapshot is immutable';
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql
    """)
    op.execute("CREATE TRIGGER offer_snapshot_immutable BEFORE UPDATE ON offers FOR EACH ROW EXECUTE FUNCTION prevent_offer_snapshot_update()")


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS offer_snapshot_immutable ON offers")
    op.execute("DROP FUNCTION IF EXISTS prevent_offer_snapshot_update()")
    for table in ("audit_events", "orders", "approvals", "offer_assessments", "evidence",
                  "offers", "requirements", "cases"):
        op.drop_table(table)
