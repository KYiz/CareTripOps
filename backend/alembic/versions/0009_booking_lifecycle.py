"""Supplier offers, evidence provenance, ranking, advisor review, payments, order lifecycle, outbox.

Also renames the demo-era statuses: DEMO_COMPLETED -> BOOKED, MOCK_BOOKING -> BOOKING,
SIMULATED_CONFIRMED -> CONFIRMED.

Revision ID: 0009_booking_lifecycle
Revises: 0008_case_language
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "0009_booking_lifecycle"
down_revision = "0008_case_language"
branch_labels = None
depends_on = None

SNAPSHOT_COLUMNS = ("case_id", "catalog_product_id", "version", "total_amount", "currency", "includes",
                    "supplier_claims", "expires_at")
NEW_SNAPSHOT_COLUMNS = SNAPSHOT_COLUMNS + ("supplier", "supplier_offer_ref", "name", "attributes", "cancellation_policy")


def _snapshot_trigger(columns) -> str:
    old = ", ".join(f"OLD.{c}" for c in columns)
    new = ", ".join(f"NEW.{c}" for c in columns)
    return f"""
    CREATE OR REPLACE FUNCTION prevent_offer_snapshot_update() RETURNS trigger AS $$
    BEGIN
      IF ROW({old}) IS DISTINCT FROM ROW({new}) THEN
        RAISE EXCEPTION 'offer snapshot is immutable';
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql
    """


def _ts(name: str, nullable: bool = False):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.add_column("offers", sa.Column("supplier", sa.String(40), nullable=False, server_default="simulator"))
    op.add_column("offers", sa.Column("supplier_offer_ref", sa.String(160)))
    op.add_column("offers", sa.Column("name", sa.String(160)))
    op.add_column("offers", sa.Column("attributes", JSONB(), nullable=False, server_default="{}"))
    op.add_column("offers", sa.Column("cancellation_policy", JSONB(), nullable=False, server_default="[]"))
    for column in ("supplier", "attributes", "cancellation_policy"):
        op.alter_column("offers", column, server_default=None)
    op.execute(_snapshot_trigger(NEW_SNAPSHOT_COLUMNS))

    op.add_column("evidence", sa.Column("source_url", sa.String(500)))
    op.add_column("evidence", sa.Column("content_hash", sa.String(64)))

    for column in (sa.Column("departure_date", sa.Date()), sa.Column("supplier_hold_ref", sa.String(80)),
                   _ts("supplier_hold_expires_at", True), sa.Column("supplier_booking_ref", sa.String(80)),
                   sa.Column("failure_reason", sa.String(80)), sa.Column("refund_amount", sa.Numeric(12, 2)),
                   _ts("cancelled_at", True)):
        op.add_column("orders", column)
    op.add_column("orders", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.alter_column("orders", "updated_at", server_default=None)
    op.execute("UPDATE orders SET status = 'CONFIRMED' WHERE status = 'SIMULATED_CONFIRMED'")
    op.execute("UPDATE cases SET status = 'BOOKED' WHERE status = 'DEMO_COMPLETED'")
    op.execute("UPDATE cases SET status = 'BOOKING' WHERE status = 'MOCK_BOOKING'")

    op.add_column("jobs", sa.Column("payload", JSONB(), nullable=False, server_default="{}"))
    op.add_column("jobs", sa.Column("run_after", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.alter_column("jobs", "payload", server_default=None)
    op.alter_column("jobs", "run_after", server_default=None)

    op.create_table(
        "offer_rankings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("offer_id", UUID(as_uuid=False), sa.ForeignKey("offers.id"), nullable=False),
        sa.Column("rank_round", sa.Integer(), nullable=False),
        sa.Column("eligible", sa.Boolean(), nullable=False),
        sa.Column("score", sa.Numeric(5, 2), nullable=False),
        sa.Column("factors", JSONB(), nullable=False),
        _ts("created_at"),
        sa.UniqueConstraint("offer_id", "rank_round"),
    )
    op.create_table(
        "review_tasks",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("case_id", UUID(as_uuid=False), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("offer_id", UUID(as_uuid=False), sa.ForeignKey("offers.id"), nullable=False),
        sa.Column("claim_type", sa.String(80), nullable=False),
        sa.Column("reason_code", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("resolution_note", sa.Text()),
        sa.Column("resolved_by", UUID(as_uuid=False), sa.ForeignKey("users.id")),
        _ts("created_at"), _ts("resolved_at", True),
    )
    op.create_index("ix_review_tasks_case_id", "review_tasks", ["case_id"])
    op.execute("CREATE UNIQUE INDEX uq_open_review ON review_tasks (offer_id, claim_type) WHERE status = 'OPEN'")
    op.create_table(
        "payments",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("order_id", UUID(as_uuid=False), sa.ForeignKey("orders.id"), nullable=False, unique=True),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("provider_ref", sa.String(120), nullable=False, unique=True),
        sa.Column("payment_intent_ref", sa.String(120)),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("refunded_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("checkout_url", sa.Text()),
        _ts("created_at"), _ts("updated_at"),
    )
    op.create_table(
        "payment_events",
        sa.Column("id", sa.String(120), primary_key=True),
        sa.Column("event_type", sa.String(80), nullable=False),
        _ts("received_at"),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("case_id", UUID(as_uuid=False), sa.ForeignKey("cases.id")),
        sa.Column("to_email", sa.String(254), nullable=False),
        sa.Column("template", sa.String(40), nullable=False),
        sa.Column("language", sa.String(5), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(200)),
        _ts("next_attempt_at"), _ts("created_at"), _ts("sent_at", True),
    )
    op.execute("CREATE INDEX ix_notifications_pending ON notifications (id) WHERE status = 'PENDING'")


def downgrade() -> None:
    for table in ("notifications", "payment_events", "payments", "review_tasks", "offer_rankings"):
        op.drop_table(table)
    op.drop_column("jobs", "run_after")
    op.drop_column("jobs", "payload")
    op.execute("UPDATE cases SET status = 'DEMO_COMPLETED' WHERE status = 'BOOKED'")
    op.execute("UPDATE cases SET status = 'MOCK_BOOKING' WHERE status = 'BOOKING'")
    op.execute("UPDATE orders SET status = 'SIMULATED_CONFIRMED' WHERE status = 'CONFIRMED'")
    for column in ("updated_at", "cancelled_at", "refund_amount", "failure_reason", "supplier_booking_ref",
                   "supplier_hold_expires_at", "supplier_hold_ref", "departure_date"):
        op.drop_column("orders", column)
    op.drop_column("evidence", "content_hash")
    op.drop_column("evidence", "source_url")
    op.execute(_snapshot_trigger(SNAPSHOT_COLUMNS))
    for column in ("cancellation_policy", "attributes", "name", "supplier_offer_ref", "supplier"):
        op.drop_column("offers", column)
