"""Case-bound guide tools and a separate, illustrative itinerary revision graph."""

from datetime import datetime, timezone
from typing import TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app.db import Case, Requirement, SessionLocal, add_event
from app.skills.contracts import DraftPlanInput
from app.skills.domain import build_draft_itinerary
from app.skills.destinations import ATTRACTION_CATALOG
from app.two_brains import planning_enabled, review_itinerary


class RevisionState(TypedDict, total=False):
    case_id: str
    request: str
    proposal_id: str
    days: list[dict]
    error: str
    model_trace: dict


def draft_days(requirement: Requirement) -> list[dict]:
    return [day.model_dump() for day in build_draft_itinerary(DraftPlanInput(
        destination=requirement.destination, destination_scope=requirement.destination_scope,
        duration_days=requirement.duration_days, attractions=requirement.attractions,
        travel_pace=requirement.travel_pace))]


def available_attractions(requirement: Requirement) -> list[str]:
    return list(dict.fromkeys([*requirement.attractions,
                               *ATTRACTION_CATALOG.get(requirement.destination or "", {}),
                               *(day["attraction"] for day in draft_days(requirement) if day["attraction"])]))


def guide_context(case_id: str) -> dict:
    with SessionLocal() as session:
        case = session.get(Case, case_id)
        if not case:
            raise LookupError("Case not found")
        requirement = session.scalar(select(Requirement).where(Requirement.case_id == case_id))
        state = case.guide_state or {}
        attractions = available_attractions(requirement) if requirement else []
        selected = state.get("selected_attraction")
        if selected not in attractions:
            selected = attractions[0] if attractions else None
        pending_plan = bool(requirement and not requirement.missing_fields and not state.get("initial_days")
                            and planning_enabled() and case.status not in {"HUMAN_REVIEW", "RECOVERY_REQUIRED", "REJECTED"})
        return {
            "case_id": case_id, "case_status": case.status,
            "destination": requirement.destination if requirement else None,
            "travel_pace": requirement.travel_pace if requirement else None,
            "traveler_count": requirement.traveler_count if requirement else None,
            "elevator_required": bool(requirement.hard_constraints.get("elevator_required")) if requirement else False,
            "attractions": attractions, "selected_attraction": selected,
            "days": [] if pending_plan else state.get("accepted_days") or state.get("initial_days") or (draft_days(requirement) if requirement else []),
            "proposal": state.get("proposal"),
            "itinerary_source": "PENDING" if pending_plan else state.get("itinerary_source", "DETERMINISTIC_DRAFT"),
            "itinerary_version": state.get("itinerary_version", 0),
            "budget": str(requirement.budget) if requirement and requirement.budget else None,
            "currency": requirement.currency if requirement else None,
            "place_sources": {name: item["source_url"] for name, item in
                              ATTRACTION_CATALOG.get(requirement.destination or "", {}).items()} if requirement else {},
            "conversation": state.get("conversation", []),
            "missing_fields": requirement.missing_fields if requirement else [],
            "location_mode": "MANUAL", "source": "CASE_REQUIREMENTS",
        }


def select_attraction(case_id: str, attraction: str) -> dict:
    with SessionLocal.begin() as session:
        case = session.get(Case, case_id, with_for_update=True)
        if not case:
            raise LookupError("Case not found")
        requirement = session.scalar(select(Requirement).where(Requirement.case_id == case_id))
        if not requirement or attraction not in available_attractions(requirement):
            raise ValueError("Select an attraction already present in this trip")
        case.guide_state = {**(case.guide_state or {}), "selected_attraction": attraction}
        add_event(session, case_id, "Travel Guide", "ATTRACTION_SELECTED", case.status,
                  {"attraction": attraction, "location_mode": "MANUAL"})
    return guide_context(case_id)


def record_guide_turn(case_id: str, role: str, text: str, source: str) -> None:
    if role not in {"traveler", "guide"} or source not in {"text", "voice"}:
        raise ValueError("Invalid conversation role or source")
    with SessionLocal.begin() as session:
        case = session.get(Case, case_id, with_for_update=True)
        if not case:
            raise LookupError("Case not found")
        previous = case.guide_state or {}
        conversation = list(previous.get("conversation", []))[-29:]
        conversation.append({"role": role, "text": text[:1000], "source": source,
                             "created_at": datetime.now(timezone.utc).isoformat()})
        case.guide_state = {**previous, "conversation": conversation}
        add_event(session, case_id, "Travel Guide", "GUIDE_TURN_SAVED", case.status,
                  {"role": role, "source": source, "length": min(len(text), 1000)})


def classify_intent(message: str) -> str:
    lowered = message.casefold()
    if any(word in lowered for word in ("hotel", "accommodation", "price", "budget", "package", "booking", "payment", "transport", "cheaper")):
        return "PACKAGE_CHANGE"
    if any(word in lowered for word in ("change", "adjust", "skip", "tired", "rest", "slower", "too much", "modify")):
        return "REVISION"
    if any(word in lowered for word in ("next", "after this", "following")):
        return "NEXT_ACTIVITY"
    return "ATTRACTION_QUESTION"


def guide_answer(context: dict, message: str) -> dict:
    intent = classify_intent(message)
    if intent == "PACKAGE_CHANGE":
        return {"intent": intent, "reply": "A change to price, hotel, transport or package needs a new trip request and fresh verification. Your current approved offer and booking remain unchanged.",
                "model_mode": "deterministic", "citations": []}
    if intent == "REVISION":
        return {"intent": intent, "reply": "I can prepare a gentler draft for you to review. This will not change a verified offer or booking.",
                "model_mode": "deterministic", "citations": []}
    if not context["destination"]:
        reply = "Start by telling us about your New Zealand trip. I can then use your trip details here."
    elif intent == "NEXT_ACTIVITY":
        days = context["days"]
        selected = context["selected_attraction"]
        index = next((i for i, day in enumerate(days) if day["attraction"] == selected), -1)
        following = next((day for day in days[index + 1:] if day["attraction"]), None)
        reply = (f"Your illustrative next stop is {following['attraction']}. Consider a rest before continuing."
                 if following else "There is no further attraction in this illustrative outline. You can take a break.")
    else:
        selected = context["selected_attraction"]
        reply = (f"{selected} is listed in your {context['destination']} trip idea. I can help you review the next step or request a gentler draft. Visit details have not been verified."
                 if selected else f"Your {context['destination']} trip is taking shape. Choose an attraction to ask about it.")
    return {"intent": intent, "reply": reply, "model_mode": "deterministic", "citations": []}


async def _prepare_revision(state: RevisionState) -> RevisionState:
    if any(term in state["request"].casefold() for term in
           ("hotel", "accommodation", "price", "budget", "package", "booking", "payment", "transport")):
        return {"error": "Package or cost changes need a new verified proposal and human review"}
    context = guide_context(state["case_id"])
    if not context["days"]:
        return {"error": "A trip outline is required before requesting a revision"}
    days = [dict(day) for day in context["days"]]
    selected = context["selected_attraction"]
    target = next((day for day in days if day["attraction"] == selected), days[0])
    target["note"] = "Gentler draft: leave time for a rest before this activity. Timing and availability require confirmation."
    if planning_enabled():
        try:
            revised, trace = await review_itinerary(state["case_id"], state["request"], context)
            return {"days": revised, "model_trace": trace}
        except Exception as exc:
            with SessionLocal.begin() as session:
                case = session.get(Case, state["case_id"])
                add_event(session, case.id, "Travel Guide", "REVISION_MODEL_FAILED", case.status,
                          {"error_type": type(exc).__name__})
            return {"error": "Gemini planning failed; the existing trip outline is unchanged"}
    return {"days": days}


def _save_revision(state: RevisionState) -> RevisionState:
    with SessionLocal.begin() as session:
        case = session.get(Case, state["case_id"], with_for_update=True)
        previous = case.guide_state or {}
        proposal = {"id": state["proposal_id"], "request": state["request"],
                    "status": "PENDING", "days": state["days"],
                    "scope": "ILLUSTRATIVE_ONLY", "model_trace": state.get("model_trace")}
        case.guide_state = {**previous, "proposal": proposal}
        add_event(session, case.id, "Travel Guide", "ITINERARY_REVISION_PROPOSED", case.status,
                  {"proposal_id": proposal["id"], "scope": proposal["scope"]})
    return {}


def _route_revision(state: RevisionState) -> str:
    return "finish" if state.get("error") else "save"


def build_revision_graph(checkpointer):
    graph = StateGraph(RevisionState)
    graph.add_node("prepare", _prepare_revision)
    graph.add_node("save", _save_revision)
    graph.add_node("finish", lambda state: {})
    graph.add_edge(START, "prepare")
    graph.add_conditional_edges("prepare", _route_revision, {"save": "save", "finish": "finish"})
    graph.add_edge("save", END)
    graph.add_edge("finish", END)
    return graph.compile(checkpointer=checkpointer)


def confirm_revision(case_id: str, proposal_id: str, accept: bool) -> dict:
    with SessionLocal.begin() as session:
        case = session.get(Case, case_id, with_for_update=True)
        if not case:
            raise LookupError("Case not found")
        state = case.guide_state or {}
        proposal = state.get("proposal")
        if not proposal or proposal["id"] != proposal_id or proposal["status"] != "PENDING":
            raise ValueError("There is no pending proposal with this ID")
        updated = {**proposal, "status": "ACCEPTED" if accept else "DECLINED"}
        next_version = int(state.get("itinerary_version", 1)) + (1 if accept else 0)
        history = list(state.get("itinerary_history", []))
        if accept:
            history.append({"version": next_version, "proposal_id": proposal_id,
                            "days": proposal["days"], "source": "GEMINI_REVIEWED" if proposal.get("model_trace") else "DETERMINISTIC_DRAFT"})
        case.guide_state = {**state, "proposal": updated,
                            **({"accepted_days": proposal["days"], "itinerary_version": next_version,
                                "itinerary_source": "GEMINI_REVIEWED" if proposal.get("model_trace") else "DETERMINISTIC_DRAFT",
                                "itinerary_history": history} if accept else {})}
        add_event(session, case_id, "Travel Guide", "ITINERARY_REVISION_DECIDED", case.status,
                  {"proposal_id": proposal_id, "decision": updated["status"],
                   "scope": "ILLUSTRATIVE_ONLY"})
    return guide_context(case_id)


def new_proposal_id() -> str:
    return str(uuid4())
