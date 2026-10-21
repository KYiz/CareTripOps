"""Migration 0007 moves guide data out of cases.guide_state without losing it, and back on downgrade."""
import json
import os
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import settings

ALEMBIC_INI = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")


def _admin_dsn():
    return make_url(settings.database_url).set(drivername="postgresql", database="postgres").render_as_string(
        hide_password=False)


def _can_create_databases():
    try:
        with psycopg.connect(_admin_dsn(), autocommit=True, connect_timeout=3) as conn:
            return bool(conn.execute("SELECT rolcreatedb OR rolsuper FROM pg_roles WHERE rolname = current_user").fetchone()[0])
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _can_create_databases(), reason="Needs PostgreSQL with CREATEDB")


@pytest.fixture
def scratch_db():
    name = f"caretrip_migration_{uuid4().hex[:10]}"
    with psycopg.connect(_admin_dsn(), autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    url = make_url(settings.database_url).set(database=name).render_as_string(hide_password=False)
    config = Config(ALEMBIC_INI)
    config.attributes["database_url"] = url
    engine = create_engine(url)
    try:
        yield config, engine
    finally:
        engine.dispose()
        with psycopg.connect(_admin_dsn(), autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


LEGACY_STATE = {
    "requirements_model_mode": "api", "requirements_provider": "gemini", "voice_draft": True,
    "spoken_answers": {"budget": "1000"}, "selected_attraction": "Sky Tower", "live_session_count": 2,
    "conversation": [{"role": "traveler", "text": "Make day two gentler", "source": "voice",
                      "created_at": "2026-10-01T10:00:00+00:00"},
                     {"role": "guide", "text": "I can prepare a gentler draft.", "source": "text",
                      "created_at": "2026-10-01T10:00:05+00:00"}],
    "initial_days": [{"day_number": 1, "title": "Harbour"}], "itinerary_model_trace": {"mode": "GEMINI_TWO_BRAINS"},
    "itinerary_error": None, "itinerary_source": "DETERMINISTIC_DRAFT", "itinerary_version": 2,
    "accepted_days": [{"day_number": 1, "title": "Gentle harbour"}],
    "itinerary_history": [{"version": 2, "proposal_id": None, "days": [{"day_number": 1, "title": "Gentle harbour"}],
                           "source": "DETERMINISTIC_DRAFT"}],
    "proposal": {"id": str(uuid4()), "request": "gentler", "status": "ACCEPTED",
                 "days": [{"day_number": 1, "title": "Gentle harbour"}], "scope": "ILLUSTRATIVE_ONLY", "model_trace": None},
}


def test_guide_state_round_trips_through_the_split(scratch_db):
    config, engine = scratch_db
    command.upgrade(config, "0006_jobs")
    case_id = str(uuid4())
    with engine.begin() as conn:
        conn.execute(text("""INSERT INTO cases (id, thread_id, original_request, status, active_node, state_version,
                                                clarification_count, llm_calls, guide_state, created_at, updated_at)
                             VALUES (:id, :thread_id, 'Auckland', 'DEMO_COMPLETED', 'review', 9, 0, 3,
                                     CAST(:state AS jsonb), now(), now())"""),
                     {"id": case_id, "thread_id": case_id, "state": json.dumps(LEGACY_STATE)})

    command.upgrade(config, "head")
    with engine.connect() as conn:
        case = conn.execute(text("SELECT * FROM cases WHERE id = :id"), {"id": case_id}).mappings().one()
        assert (case["requirements_model_mode"], case["requirements_provider"], case["voice_draft"]) == ("api", "gemini", True)
        assert case["spoken_answers"] == {"budget": "1000"} and case["selected_attraction"] == "Sky Tower"
        assert case["live_session_count"] == 2 and "guide_state" not in case
        turns = conn.execute(text("SELECT role, source, text FROM conversation_turns WHERE case_id = :id ORDER BY id"),
                             {"id": case_id}).all()
        assert [tuple(t) for t in turns] == [("traveler", "voice", "Make day two gentler"),
                                             ("guide", "text", "I can prepare a gentler draft.")]
        versions = conn.execute(text("SELECT version, source, days FROM itinerary_versions WHERE case_id = :id ORDER BY version"),
                                {"id": case_id}).all()
        # The initial outline had a planner trace, so it was Gemini reviewed; version 2 is the accepted revision.
        assert [(v.version, v.source) for v in versions] == [(1, "GEMINI_REVIEWED"), (2, "DETERMINISTIC_DRAFT")]
        assert versions[1].days == [{"day_number": 1, "title": "Gentle harbour"}]
        assert conn.execute(text("SELECT status FROM itinerary_proposals WHERE case_id = :id"),
                            {"id": case_id}).scalar_one() == "ACCEPTED"

    command.downgrade(config, "0006_jobs")
    with engine.connect() as conn:
        state = conn.execute(text("SELECT guide_state FROM cases WHERE id = :id"), {"id": case_id}).scalar_one()
    assert state["accepted_days"] == LEGACY_STATE["accepted_days"]
    assert state["initial_days"] == LEGACY_STATE["initial_days"]
    assert state["itinerary_version"] == 2 and state["selected_attraction"] == "Sky Tower"
    assert [turn["text"] for turn in state["conversation"]] == ["Make day two gentler", "I can prepare a gentler draft."]
    assert state["proposal"]["status"] == "ACCEPTED"
