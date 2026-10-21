"""Planning nodes: requirements, clarification and the illustrative itinerary."""

from langgraph.types import interrupt
from sqlalchemy import select

from app import case_state
from app.config import settings
from app.db import Case, Requirement, SessionLocal, add_event, set_status
from app.skills.contracts import RequirementInput, RequirementOutput
from app.skills.destinations import ATTRACTION_CATALOG, ATTRACTIONS, resolve_attractions, resolve_destination
from app.skills.domain import extract_requirements, validate_requirements
from app.skills.model_adapter import extract_requirements_live
from app.two_brains import planning_enabled, review_itinerary
from app.workflow.state import FlowState, owner_needs, requirements_from_row


def _extract_with_model(case_id: str, input_data: RequirementInput) -> RequirementOutput | None:
    """One bounded model call. On a limit or provider error the Case goes to a person; no mock fallback."""
    with SessionLocal.begin() as session:
        case = session.get(Case, case_id, with_for_update=True)
        if case.llm_calls >= settings.max_llm_calls:
            set_status(session, case, "HUMAN_REVIEW", "requirements_worker", "Requirements Worker", "MODEL_CALL_LIMIT", {})
            return None
        case.llm_calls += 1
        add_event(session, case.id, "Requirements Worker", "MODEL_CALL_STARTED", case.status, {"call_number": case.llm_calls})
    try:
        extracted, usage = extract_requirements_live(input_data)
    except Exception as exc:
        with SessionLocal.begin() as session:
            set_status(session, session.get(Case, case_id, with_for_update=True), "HUMAN_REVIEW", "requirements_worker",
                       "Requirements Worker", "MODEL_ERROR", {"error_type": type(exc).__name__})
        return None
    with SessionLocal.begin() as session:
        add_event(session, case_id, "Requirements Worker", "MODEL_USAGE", "RECEIVED",
                  {key: value for key, value in usage.items() if value is not None})
    # Our own vocabulary decides the destination and attractions; the model only fills the numbers.
    mentioned, request_scope = resolve_destination(input_data.request)
    extracted.destination, extracted.destination_scope = (
        (mentioned, request_scope) if request_scope != "UNKNOWN" else resolve_destination(extracted.destination or ""))
    extracted.attractions = resolve_attractions(input_data.request, extracted.destination)
    extracted.travel_pace = extract_requirements(input_data).travel_pace
    if extracted.currency:
        extracted.currency = extracted.currency.strip().upper()
    extracted.missing_fields = validate_requirements(extracted)
    return extracted


def requirements_worker(state: FlowState) -> FlowState:
    with SessionLocal() as session:
        case = session.get(Case, state["case_id"])
        existing = session.scalar(select(Requirement).where(Requirement.case_id == case.id))
        input_data = RequirementInput(request=case.original_request, demo_date=case.demo_date)
    extracted = None
    if existing is None and settings.model_mode == "api" and not case.voice_draft:
        extracted = _extract_with_model(state["case_id"], input_data)
        if extracted is None:
            return {"model_error": True, "missing_fields": ["model_error"]}
    elif existing is None:
        extracted = extract_requirements(input_data)
    with SessionLocal.begin() as session:
        case = session.get(Case, state["case_id"], with_for_update=True)
        row = session.scalar(select(Requirement).where(Requirement.case_id == case.id))
        if row is None:
            row = Requirement(case_id=case.id, destination=extracted.destination,
                              destination_scope=extracted.destination_scope,
                              attractions=extracted.attractions, travel_pace=extracted.travel_pace,
                              departure_date=extracted.departure_date, traveler_count=extracted.traveler_count,
                              duration_days=extracted.duration_days, budget=extracted.budget,
                              currency=extracted.currency,
                              hard_constraints={"elevator_required": extracted.elevator_required,
                                                "needs": owner_needs(session, case.id)},
                              missing_fields=extracted.missing_fields)
            session.add(row)
        canonical, scope = resolve_destination(row.destination or case.original_request)
        row.destination = canonical
        row.destination_scope = scope
        if scope == "OUTSIDE_NZ":
            row.missing_fields = []
            set_status(session, case, "HUMAN_REVIEW", "requirements_worker", "Requirements Worker",
                       "DESTINATION_OUTSIDE_NZ", {"message": "This demo currently supports travel within New Zealand only."})
            return {"unsupported_destination": True, "missing_fields": []}
        current = requirements_from_row(row)
        missing = validate_requirements(current)
        row.missing_fields = missing
        if missing:
            set_status(session, case, "NEEDS_CLARIFICATION", "requirements_worker", "Requirements Worker",
                       "REQUIREMENTS_INCOMPLETE", {"missing_fields": missing})
        else:
            set_status(session, case, "REQUIREMENTS_READY", "requirements_worker", "Requirements Worker",
                       "REQUIREMENTS_VALIDATED", {"destination": row.destination, "currency": row.currency})
        return {"missing_fields": missing}


def route_requirements(state: FlowState) -> str:
    if state.get("model_error") or state.get("unsupported_destination"):
        return "human_review"
    if not state.get("missing_fields"):
        return "itinerary"
    with SessionLocal() as session:
        case = session.get(Case, state["case_id"])
        return "human_review" if case.clarification_count >= settings.max_clarifications else "wait_clarification"


def wait_clarification(state: FlowState) -> FlowState:
    interrupt({"type": "clarification", "missing_fields": state["missing_fields"]})
    return {}


async def itinerary_worker(state: FlowState) -> FlowState:
    with SessionLocal() as session:
        case = session.get(Case, state["case_id"])
        row = session.scalar(select(Requirement).where(Requirement.case_id == case.id))
        if case_state.current_itinerary(session, case.id):
            return {}
        baseline = case_state.draft_days(row, case.language, case.original_request)
        allowed = list(dict.fromkeys([*row.attractions, *ATTRACTION_CATALOG.get(row.destination or "", {}),
                                      *ATTRACTIONS.get(row.destination or "", {})]))
        context = {"destination": row.destination, "travel_pace": row.travel_pace, "language": case.language,
                   "traveler_count": row.traveler_count, "budget": str(row.budget),
                   "currency": row.currency, "elevator_required": bool(row.hard_constraints.get("elevator_required")),
                   # Planning hints only: no medical notes, contacts, names or emails go to a model.
                   "access_needs": case_state.access_needs(row),
                   "attractions": allowed, "days": baseline,
                   "place_sources": {name: item["source_url"] for name, item in
                                     ATTRACTION_CATALOG.get(row.destination or "", {}).items()}}
        original_request = case.original_request
    days, source, trace, error = baseline, "DETERMINISTIC_DRAFT", None, None
    if planning_enabled():
        try:
            days, trace = await review_itinerary(state["case_id"], original_request, context)
            source = "GEMINI_REVIEWED"
        except Exception as exc:
            source, error = "GEMINI_FAILED", type(exc).__name__
    with SessionLocal.begin() as session:
        case = session.get(Case, state["case_id"], with_for_update=True)
        # A replayed run must not add a second initial outline.
        if case_state.add_itinerary_version(session, case.id, days, source, model_trace=trace, error=error,
                                            only_if_first=True):
            add_event(session, case.id, "Travel Planner", "ITINERARY_GENERATED" if not error else "ITINERARY_MODEL_FAILED",
                      case.status, {"source": source, "version": 1, "error_type": error})
    return {}

