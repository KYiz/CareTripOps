"""Case-bound guide tools and a separate, illustrative itinerary revision graph."""

from datetime import datetime, timezone
from typing import TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app import case_state
from app.db import (Approval, Case, Evidence, ItineraryProposal, Offer, Order, Requirement, SessionLocal, add_event,
                    latest_claims)
from app.skills.destinations import ATTRACTION_CATALOG, local_name
from app.guide_text import CLAIM_NAMES, GENTLER_NOTE, classify_intent, reply_text
from app.two_brains import planning_enabled, review_itinerary


class RevisionState(TypedDict, total=False):
    case_id: str
    request: str
    proposal_id: str
    days: list[dict]
    error: str
    model_trace: dict


def available_attractions(requirement: Requirement) -> list[str]:
    return list(dict.fromkeys([*requirement.attractions,
                               *ATTRACTION_CATALOG.get(requirement.destination or "", {}),
                               *(day["attraction"] for day in case_state.draft_days(requirement) if day["attraction"])]))


def guide_context(case_id: str) -> dict:
    with SessionLocal() as session:
        case = session.get(Case, case_id)
        if not case:
            raise LookupError("Case not found")
        requirement = session.scalar(select(Requirement).where(Requirement.case_id == case_id))
        itinerary = case_state.current_itinerary(session, case_id)
        attractions = available_attractions(requirement) if requirement else []
        selected = case.selected_attraction
        if selected not in attractions:
            selected = attractions[0] if attractions else None
        pending_plan = bool(requirement and not requirement.missing_fields and not itinerary
                            and planning_enabled() and case.status not in {"HUMAN_REVIEW", "RECOVERY_REQUIRED", "REJECTED"})
        return {
            "case_id": case_id, "case_status": case.status,
            "destination": requirement.destination if requirement else None,
            "travel_pace": requirement.travel_pace if requirement else None,
            "traveler_count": requirement.traveler_count if requirement else None,
            "elevator_required": bool(requirement.hard_constraints.get("elevator_required")) if requirement else False,
            "access_needs": case_state.access_needs(requirement),
            "attractions": attractions, "selected_attraction": selected,
            "days": [] if pending_plan else itinerary.days if itinerary else (case_state.draft_days(requirement, case.language, case.original_request) if requirement else []),
            "proposal": case_state.proposal_payload(case_state.latest_proposal(session, case_id)),
            "itinerary_source": "PENDING" if pending_plan else itinerary.source if itinerary else "DETERMINISTIC_DRAFT",
            "itinerary_version": itinerary.version if itinerary else 0,
            "budget": str(requirement.budget) if requirement and requirement.budget else None,
            "currency": requirement.currency if requirement else None,
            "place_sources": {name: item["source_url"] for name, item in
                              ATTRACTION_CATALOG.get(requirement.destination or "", {}).items()} if requirement else {},
            "conversation": case_state.conversation(session, case_id),
            "stay": chosen_stay(session, case_id),
            "missing_fields": requirement.missing_fields if requirement else [],
            "location_mode": "MANUAL", "source": "CASE_REQUIREMENTS", "language": case.language,
        }


def chosen_stay(session, case_id: str) -> dict | None:
    """The booked offer, or the one waiting for approval, with what was verified and the evidence behind it."""
    offer_id = session.scalar(select(Order.offer_id).where(Order.case_id == case_id, Order.status == "CONFIRMED")
                              .order_by(Order.created_at.desc()).limit(1)) or \
        session.scalar(select(Approval.offer_id).where(Approval.case_id == case_id,
                                                       Approval.status.in_(("PENDING", "APPROVED")))
                       .order_by(Approval.created_at.desc()).limit(1))
    offer = offer_id and session.get(Offer, offer_id)
    if not offer:
        return None
    verified = [claim for claim, row in latest_claims(session, offer.id).items() if row.verdict == "PASS"]
    evidence = session.scalars(select(Evidence).where(Evidence.offer_id == offer.id, Evidence.claim_type.in_(verified),
                                                      Evidence.polarity == "SUPPORT")
                               .order_by(Evidence.source_reference)).all()
    return {"name": offer.name or offer.catalog_product_id, "verified_claims": verified,
            "evidence": [{"claim": e.claim_type, "reference": e.source_reference, "detail": e.detail, "url": e.source_url}
                         for e in evidence]}


def select_attraction(case_id: str, attraction: str) -> dict:
    with SessionLocal.begin() as session:
        case = session.get(Case, case_id, with_for_update=True)
        if not case:
            raise LookupError("Case not found")
        requirement = session.scalar(select(Requirement).where(Requirement.case_id == case_id))
        if not requirement or attraction not in available_attractions(requirement):
            raise ValueError("Select an attraction already present in this trip")
        case.selected_attraction = attraction
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
        case_state.add_turn(session, case_id, role, text, source)
        add_event(session, case_id, "Travel Guide", "GUIDE_TURN_SAVED", case.status,
                  {"role": role, "source": source, "length": min(len(text), 1000)})


def guide_answer(context: dict, message: str, lang: str = "en") -> dict:
    intent = classify_intent(message)
    if intent == "PACKAGE_CHANGE":
        return {"intent": intent, "reply": reply_text(lang, "package"), "model_mode": "deterministic", "citations": []}
    if intent == "REVISION":
        return {"intent": intent, "reply": reply_text(lang, "revision"), "model_mode": "deterministic", "citations": []}
    sources = context.get("place_sources", {})

    def place_citation(place: str | None) -> list[dict]:
        return [{"kind": "PLACE", "title": local_name(place, lang), "url": sources[place]}] if place in sources else []

    citations: list[dict] = []
    if intent == "ACCESS_QUESTION":
        reply, citations = _access_answer(context.get("stay"), lang)
    elif not context["destination"]:
        reply = reply_text(lang, "no_trip")
    elif intent == "NEXT_ACTIVITY":
        days = context["days"]
        selected = context["selected_attraction"]
        index = next((i for i, day in enumerate(days) if day["attraction"] == selected), -1)
        following = next((day for day in days[index + 1:] if day["attraction"]), None)
        reply = (reply_text(lang, "next", place=local_name(following["attraction"], lang)) if following
                 else reply_text(lang, "no_next"))
        citations = place_citation(following["attraction"]) if following else []
    else:
        selected = context["selected_attraction"]
        destination = local_name(context["destination"], lang)
        reply = (reply_text(lang, "place", place=local_name(selected, lang), destination=destination) if selected
                 else reply_text(lang, "no_place", destination=destination))
        citations = place_citation(selected)
    return {"intent": intent, "reply": reply, "model_mode": "deterministic", "citations": citations}


def _access_answer(stay: dict | None, lang: str) -> tuple[str, list[dict]]:
    """Only what was verified for the chosen stay, each fact with the evidence behind it; never a guess."""
    if not stay:
        return reply_text(lang, "access_none"), []
    claims = [CLAIM_NAMES[lang][claim] for claim in stay["verified_claims"] if claim in CLAIM_NAMES[lang]]
    if not claims:
        return reply_text(lang, "access_no_need", stay=stay["name"]), []
    joiner = "、" if lang == "zh" else ", "
    citations = [{"kind": "EVIDENCE", "title": f"{item['reference']}: {item['detail']}", "url": item["url"]}
                 for item in stay["evidence"]]
    return reply_text(lang, "access", stay=stay["name"], claims=joiner.join(claims)), citations


async def _prepare_revision(state: RevisionState) -> RevisionState:
    if classify_intent(state["request"]) == "PACKAGE_CHANGE":
        return {"error": "Package or cost changes need a new verified proposal and human review"}
    context = guide_context(state["case_id"])
    if not context["days"]:
        return {"error": "A trip outline is required before requesting a revision"}
    days = [dict(day) for day in context["days"]]
    selected = context["selected_attraction"]
    target = next((day for day in days if day["attraction"] == selected), days[0])
    target["note"] = GENTLER_NOTE[context["language"]]
    if planning_enabled():
        try:
            revised, trace = await review_itinerary(state["case_id"], state["request"], context, revision=True)
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
        case_state.propose(session, case.id, state["proposal_id"], state["request"], state["days"],
                           state.get("model_trace"))
        add_event(session, case.id, "Travel Guide", "ITINERARY_REVISION_PROPOSED", case.status,
                  {"proposal_id": state["proposal_id"], "scope": "ILLUSTRATIVE_ONLY"})
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
        proposal = session.get(ItineraryProposal, proposal_id, with_for_update=True)
        if not proposal or proposal.case_id != case_id or proposal.status != "PENDING":
            raise ValueError("There is no pending proposal with this ID")
        proposal.status = "ACCEPTED" if accept else "DECLINED"
        proposal.decided_at = datetime.now(timezone.utc)
        if accept:
            if not case_state.current_itinerary(session, case_id):
                # Version 1 is the outline the proposal revised, so history stays complete.
                requirement = session.scalar(select(Requirement).where(Requirement.case_id == case_id))
                case_state.add_itinerary_version(session, case_id, case_state.draft_days(
                    requirement, case.language, case.original_request), "DETERMINISTIC_DRAFT")
                session.flush()
            case_state.add_itinerary_version(
                session, case_id, proposal.days, "GEMINI_REVIEWED" if proposal.model_trace else "DETERMINISTIC_DRAFT",
                model_trace=proposal.model_trace, proposal_id=proposal_id)
        add_event(session, case_id, "Travel Guide", "ITINERARY_REVISION_DECIDED", case.status,
                  {"proposal_id": proposal_id, "decision": proposal.status,
                   "scope": "ILLUSTRATIVE_ONLY"})
    return guide_context(case_id)


def new_proposal_id() -> str:
    return str(uuid4())
