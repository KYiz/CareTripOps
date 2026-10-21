"""Split cases.guide_state into columns and tables.

The JSONB blob held the conversation, every itinerary version, the revision proposal and several
scalar flags, and each writer replaced it whole. Rows can now be queried, constrained and written
independently. Existing data is copied before the column is dropped.

Revision ID: 0007_split_guide_state
Revises: 0006_jobs
"""
import json
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "0007_split_guide_state"
down_revision = "0006_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("requirements_model_mode", sa.String(20), nullable=False, server_default="mock_llm"))
    op.add_column("cases", sa.Column("requirements_provider", sa.String(20)))
    op.add_column("cases", sa.Column("voice_draft", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("cases", sa.Column("spoken_answers", JSONB(), nullable=False, server_default="{}"))
    op.add_column("cases", sa.Column("selected_attraction", sa.String(120)))
    op.add_column("cases", sa.Column("live_session_count", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "conversation_turns",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("case_id", UUID(as_uuid=False), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("source", sa.String(10), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_conversation_turns_case_id", "conversation_turns", ["case_id"])
    op.create_table(
        "itinerary_versions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("case_id", UUID(as_uuid=False), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("days", JSONB(), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("model_trace", JSONB()),
        sa.Column("error", sa.String(80)),
        sa.Column("proposal_id", UUID(as_uuid=False)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("case_id", "version"),
    )
    op.create_table(
        "itinerary_proposals",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("case_id", UUID(as_uuid=False), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("request", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("days", JSONB(), nullable=False),
        sa.Column("model_trace", JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_itinerary_proposals_case_id", "itinerary_proposals", ["case_id"])
    op.execute("CREATE UNIQUE INDEX uq_pending_proposal_case ON itinerary_proposals (case_id) WHERE status = 'PENDING'")

    bind = op.get_bind()
    now = datetime.now(timezone.utc)
    for case_id, state, created in bind.execute(sa.text("SELECT id, guide_state, created_at FROM cases")).all():
        _copy_case(bind, case_id, state or {}, created or now)

    for column in ("requirements_model_mode", "voice_draft", "spoken_answers", "live_session_count"):
        op.alter_column("cases", column, server_default=None)
    op.drop_column("cases", "guide_state")


def _copy_case(bind, case_id: str, state: dict, created: datetime) -> None:
    bind.execute(sa.text("""
        UPDATE cases SET requirements_model_mode = :mode, requirements_provider = :provider,
               voice_draft = :voice, spoken_answers = CAST(:spoken AS jsonb),
               selected_attraction = :selected, live_session_count = :live
        WHERE id = :id"""), {
        "id": case_id, "mode": state.get("requirements_model_mode") or "mock_llm",
        "provider": state.get("requirements_provider"), "voice": bool(state.get("voice_draft")),
        "spoken": json.dumps(state.get("spoken_answers") or {}),
        "selected": (state.get("selected_attraction") or None) and str(state["selected_attraction"])[:120],
        "live": int(state.get("live_session_count") or 0)})
    for turn in state.get("conversation") or []:
        bind.execute(sa.text("""INSERT INTO conversation_turns (case_id, role, source, text, created_at)
                                VALUES (:case_id, :role, :source, :text, :created_at)"""), {
            "case_id": case_id, "role": turn.get("role", "guide"), "source": turn.get("source", "text"),
            "text": turn.get("text", ""), "created_at": turn.get("created_at") or created})
    versions = []
    history = state.get("itinerary_history") or []
    if state.get("initial_days"):
        # itinerary_source described the *current* outline; once a revision was accepted, the initial
        # outline's source has to be inferred from what the planner recorded about it.
        initial_source = (state.get("itinerary_source", "DETERMINISTIC_DRAFT") if not history
                          else "GEMINI_REVIEWED" if state.get("itinerary_model_trace")
                          else "GEMINI_FAILED" if state.get("itinerary_error") else "DETERMINISTIC_DRAFT")
        versions.append({"version": 1, "days": state["initial_days"], "source": initial_source,
                         "trace": state.get("itinerary_model_trace"), "error": state.get("itinerary_error"),
                         "proposal_id": None})
    for item in history:
        versions.append({"version": item["version"], "days": item["days"], "source": item.get("source", "DETERMINISTIC_DRAFT"),
                         "trace": None, "error": None, "proposal_id": item.get("proposal_id")})
    for item in versions:
        bind.execute(sa.text("""INSERT INTO itinerary_versions (case_id, version, days, source, model_trace, error, proposal_id, created_at)
                                VALUES (:case_id, :version, CAST(:days AS jsonb), :source, CAST(:trace AS jsonb), :error, :proposal_id, :created_at)
                                ON CONFLICT (case_id, version) DO NOTHING"""), {
            "case_id": case_id, "version": item["version"], "days": json.dumps(item["days"]), "source": item["source"],
            "trace": json.dumps(item["trace"]) if item["trace"] else None, "error": item["error"],
            "proposal_id": item["proposal_id"], "created_at": created})
    proposal = state.get("proposal")
    if proposal and proposal.get("id"):
        bind.execute(sa.text("""INSERT INTO itinerary_proposals (id, case_id, request, status, days, model_trace, created_at)
                                VALUES (:id, :case_id, :request, :status, CAST(:days AS jsonb), CAST(:trace AS jsonb), :created_at)"""), {
            "id": proposal["id"], "case_id": case_id, "request": proposal.get("request", ""),
            "status": proposal.get("status", "PENDING"), "days": json.dumps(proposal.get("days") or []),
            "trace": json.dumps(proposal["model_trace"]) if proposal.get("model_trace") else None, "created_at": created})


def downgrade() -> None:
    op.add_column("cases", sa.Column("guide_state", JSONB(), nullable=False, server_default="{}"))
    bind = op.get_bind()
    for row in bind.execute(sa.text("""SELECT id, requirements_model_mode, requirements_provider, voice_draft,
                                              spoken_answers, selected_attraction, live_session_count FROM cases""")).all():
        state = {"requirements_model_mode": row.requirements_model_mode, "requirements_provider": row.requirements_provider,
                 "voice_draft": row.voice_draft, "spoken_answers": row.spoken_answers,
                 "live_session_count": row.live_session_count}
        if row.selected_attraction:
            state["selected_attraction"] = row.selected_attraction
        turns = bind.execute(sa.text("SELECT role, source, text, created_at FROM conversation_turns "
                                     "WHERE case_id = :id ORDER BY id DESC LIMIT 30"), {"id": row.id}).all()
        state["conversation"] = [{"role": t.role, "source": t.source, "text": t.text,
                                  "created_at": t.created_at.isoformat()} for t in reversed(turns)]
        versions = bind.execute(sa.text("SELECT version, days, source, model_trace, error, proposal_id "
                                        "FROM itinerary_versions WHERE case_id = :id ORDER BY version"), {"id": row.id}).all()
        if versions:
            first, last = versions[0], versions[-1]
            state.update({"initial_days": first.days, "itinerary_model_trace": first.model_trace,
                          "itinerary_error": first.error, "itinerary_version": last.version,
                          "itinerary_source": last.source})
            if len(versions) > 1:
                state["accepted_days"] = last.days
                state["itinerary_history"] = [{"version": v.version, "proposal_id": v.proposal_id, "days": v.days,
                                               "source": v.source} for v in versions[1:]]
        proposal = bind.execute(sa.text("SELECT id, request, status, days, model_trace FROM itinerary_proposals "
                                        "WHERE case_id = :id ORDER BY created_at DESC LIMIT 1"), {"id": row.id}).first()
        if proposal:
            state["proposal"] = {"id": proposal.id, "request": proposal.request, "status": proposal.status,
                                 "days": proposal.days, "scope": "ILLUSTRATIVE_ONLY", "model_trace": proposal.model_trace}
        bind.execute(sa.text("UPDATE cases SET guide_state = CAST(:state AS jsonb) WHERE id = :id"),
                     {"id": row.id, "state": json.dumps(state, default=str)})
    op.alter_column("cases", "guide_state", server_default=None)
    op.drop_table("itinerary_proposals")
    op.drop_table("itinerary_versions")
    op.drop_table("conversation_turns")
    for column in ("live_session_count", "selected_attraction", "spoken_answers", "voice_draft",
                   "requirements_provider", "requirements_model_mode"):
        op.drop_column("cases", column)
