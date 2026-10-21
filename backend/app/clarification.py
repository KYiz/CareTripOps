"""Filling in missing trip details, typed into a form or said to the guide."""

from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import select

from app import case_state, config, jobs
from app.db import Case, Requirement, SessionLocal, add_event
from app.errors import fail
from app.guide_text import reply_text
from app.skills.contracts import RequirementInput
from app.skills.destinations import resolve_attractions, resolve_destination
from app.skills.domain import extract_requirements, normalize_currency
from app.skills.model_adapter import extract_requirements_live

FIELDS = {"destination", "departure_date", "traveler_count", "duration_days", "budget", "currency"}


def _parse(key: str, value):
    try:
        if key == "departure_date":
            return date.fromisoformat(str(value))
        if key in {"traveler_count", "duration_days"}:
            number = int(value)
            if number < 1:
                raise ValueError()
            return number
        if key == "budget":
            amount = Decimal(str(value))
            if amount <= 0:
                raise ValueError()
            return amount
        if key == "currency":
            currency = normalize_currency(str(value))
            if currency != "NZD":
                fail("INVALID_CURRENCY", "This New Zealand demo requires NZD", 422)
            return currency
        return str(value).strip()
    except (ValueError, InvalidOperation, TypeError):
        fail("INVALID_CLARIFICATION", f"Invalid value for {key}", 400)


def apply(case_id: str, answers: dict) -> dict:
    """Store the answers and resume the run that asked for them, in one transaction."""
    if not answers or not set(answers) <= FIELDS:
        fail("INVALID_CLARIFICATION", "Unsupported clarification fields", 400)
    with SessionLocal.begin() as session:
        case = session.get(Case, case_id, with_for_update=True)
        if not case or case.status != "NEEDS_CLARIFICATION":
            fail("INVALID_STATE", "Case is not waiting for clarification")
        if case.clarification_count >= config.settings.max_clarifications:
            fail("CLARIFICATION_LIMIT", "Clarification limit reached", 429)
        req = session.scalar(select(Requirement).where(Requirement.case_id == case_id))
        for key, raw in answers.items():
            value = _parse(key, raw)
            setattr(req, key, value)
            if key == "destination":
                req.destination, req.destination_scope = resolve_destination(value)
                if req.destination_scope == "OUTSIDE_NZ":
                    fail("DESTINATION_OUTSIDE_NZ", "This demo currently supports travel within New Zealand only", 422)
        case.clarification_count += 1
        add_event(session, case.id, "Requirements Worker", "CLARIFICATION_RECEIVED", case.status, {"fields": list(answers)})
        try:
            jobs.enqueue(session, case_id, "resume")
        except jobs.JobAlreadyActive:
            # The run that asked the question has not reached its pause point yet.
            fail("GRAPH_NOT_PAUSED", "The trip is still being prepared. Please try again in a moment.", retryable=True)
    return {"case_id": case_id, "accepted": True}


def from_speech(case_id: str, message: str, lang: str = "en") -> dict | None:
    """Collect missing details from a guide message. None when the trip is not waiting for details."""
    settings = config.settings
    with SessionLocal() as session:
        case = session.get(Case, case_id)
        if not case or case.status != "NEEDS_CLARIFICATION":
            return None
        missing = list(session.scalar(select(Requirement).where(Requirement.case_id == case_id)).missing_fields)
        heard = dict(case.spoken_answers or {})
        voice_draft, demo_date = case.voice_draft, case.demo_date
        traveler_said = case_state.traveler_turns(session, case_id)
    parsed = extract_requirements(RequirementInput(request=message.ljust(8), demo_date=demo_date))
    if parsed.destination_scope == "OUTSIDE_NZ":
        return {"saved": False, "error": reply_text(lang, "outside_nz")}
    for field in missing:
        value = getattr(parsed, field, None)
        if value is not None:
            heard[field] = str(value) if field in {"budget", "departure_date"} else value
    with SessionLocal.begin() as session:
        case = session.get(Case, case_id, with_for_update=True)
        case.spoken_answers = heard
        add_event(session, case_id, "Requirements Worker", "CLARIFICATION_DRAFTED", case.status, {"fields": sorted(heard)})
    remaining = [field for field in missing if field not in heard]
    if remaining:
        return {"saved": False, "remaining": remaining}
    if voice_draft and settings.model_mode == "api":
        error = _confirm_with_model(case_id, " ".join(traveler_said), heard, demo_date, lang)
        if error:
            return {"saved": False, "error": error}
    apply(case_id, {field: heard[field] for field in missing})
    return {"saved": True, "fields": missing}


def _confirm_with_model(case_id: str, full_request: str, heard: dict, demo_date, lang: str) -> str | None:
    """A trip started by voice gets one model pass over everything said; returns an error reply or None."""
    with SessionLocal.begin() as session:
        case = session.get(Case, case_id, with_for_update=True)
        if case.llm_calls >= config.settings.max_llm_calls:
            return reply_text(lang, "model_limit")
        case.llm_calls += 1
        add_event(session, case_id, "Requirements Worker", "MODEL_CALL_STARTED", case.status,
                  {"role": "voice_requirements", "call_number": case.llm_calls})
    try:
        result, usage = extract_requirements_live(RequirementInput(request=full_request.ljust(8), demo_date=demo_date))
    except Exception as exc:
        with SessionLocal.begin() as session:
            add_event(session, case_id, "Requirements Worker", "MODEL_ERROR", session.get(Case, case_id).status,
                      {"role": "voice_requirements", "error_type": type(exc).__name__})
        return reply_text(lang, "model_failed")
    if result.destination_scope == "OUTSIDE_NZ":
        return reply_text(lang, "outside_nz")
    if result.destination and heard.get("destination") and result.destination != heard["destination"]:
        return reply_text(lang, "two_destinations")
    with SessionLocal.begin() as session:
        case = session.get(Case, case_id, with_for_update=True)
        req = session.scalar(select(Requirement).where(Requirement.case_id == case_id))
        req.attractions = resolve_attractions(full_request, heard.get("destination"))
        req.travel_pace = extract_requirements(RequirementInput(request=full_request.ljust(8))).travel_pace
        req.hard_constraints = {**req.hard_constraints, "elevator_required": result.elevator_required}
        case.original_request, case.voice_draft = full_request, False
        add_event(session, case_id, "Requirements Worker", "MODEL_USAGE", case.status,
                  {key: value for key, value in usage.items() if value is not None})
    return None
