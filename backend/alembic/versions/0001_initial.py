"""Initial eight-table business schema.

Revision ID: 0001_initial
Revises:
"""
from alembic import op

from app.db import Base


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    Base.metadata.create_all(bind=op.get_bind())
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
    Base.metadata.drop_all(bind=op.get_bind())
