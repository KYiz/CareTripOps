from datetime import datetime, timezone
from decimal import Decimal
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from sqlalchemy import select

from app.config import settings
from app.db import (
    Approval, Case, Evidence, Offer, OfferAssessment, Order, Requirement,
    SessionLocal, add_event, set_status,
)
from app.skills.contracts import ApprovalInput, BookingInput, DraftPlanInput, RankingInput, RequirementInput, RequirementOutput, ReviewInput
from app.skills.domain import (
    build_draft_itinerary, compare_offers, extract_requirements, generate_review, rerank_offers,
    search_suppliers, validate_requirements, verify_evidence, infer_interest_tags,
)
from app.skills.destinations import resolve_destination, resolve_attractions
from app.skills.destinations import ATTRACTION_CATALOG, ATTRACTIONS
from app.skills.effects import execute_mock_booking, prepare_approval
from app.skills.model_adapter import extract_requirements_live
from app.two_brains import planning_enabled, review_itinerary


class FlowState(TypedDict, total=False):
    case_id: str
    candidate_id: str
    excluded_ids: list[str]
    rerank_count: int
    verdict: str
    final_offer_id: str
    approval_id: str
    order_id: str
    missing_fields: list[str]
    should_rerank: bool
    model_error: bool
    unsupported_destination: bool


def _requirements_from_row(row: Requirement) -> RequirementOutput:
    return RequirementOutput(destination=row.destination, destination_scope=row.destination_scope,
                             attractions=row.attractions, travel_pace=row.travel_pace,
                             departure_date=row.departure_date,
                             traveler_count=row.traveler_count, duration_days=row.duration_days,
                             budget=row.budget, currency=row.currency,
                             elevator_required=bool(row.hard_constraints.get("elevator_required")),
                             missing_fields=row.missing_fields)


def requirements_worker(state: FlowState) -> FlowState:
    with SessionLocal() as session:
        case = session.get(Case, state["case_id"])
        existing = session.scalar(select(Requirement).where(Requirement.case_id == case.id))
        input_data = RequirementInput(request=case.original_request, demo_date=case.demo_date)
    extracted = None
    if existing is None and settings.model_mode == "api" and not (case.guide_state or {}).get("voice_draft"):
        with SessionLocal.begin() as session:
            case = session.get(Case, state["case_id"], with_for_update=True)
            if case.llm_calls >= settings.max_llm_calls:
                set_status(session, case, "HUMAN_REVIEW", "requirements_worker", "Requirements Worker",
                           "MODEL_CALL_LIMIT", {})
                return {"model_error": True, "missing_fields": ["model_error"]}
            case.llm_calls += 1
            add_event(session, case.id, "Requirements Worker", "MODEL_CALL_STARTED", case.status,
                      {"call_number": case.llm_calls})
        try:
            extracted, usage = extract_requirements_live(input_data)
        except Exception as exc:
            with SessionLocal.begin() as session:
                case = session.get(Case, state["case_id"], with_for_update=True)
                set_status(session, case, "HUMAN_REVIEW", "requirements_worker", "Requirements Worker",
                           "MODEL_ERROR", {"error_type": type(exc).__name__})
            return {"model_error": True, "missing_fields": ["model_error"]}
        with SessionLocal.begin() as session:
            add_event(session, state["case_id"], "Requirements Worker", "MODEL_USAGE", "RECEIVED",
                      {key: value for key, value in usage.items() if value is not None})
        mentioned, request_scope = resolve_destination(input_data.request)
        canonical, scope = (mentioned, request_scope) if request_scope != "UNKNOWN" else resolve_destination(extracted.destination or "")
        extracted.destination = canonical
        extracted.destination_scope = scope
        extracted.attractions = resolve_attractions(input_data.request, canonical)
        extracted.travel_pace = extract_requirements(input_data).travel_pace
        if extracted.currency:
            extracted.currency = extracted.currency.strip().upper()
        extracted.missing_fields = validate_requirements(extracted)
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
                              hard_constraints={"elevator_required": extracted.elevator_required},
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
        current = _requirements_from_row(row)
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
        saved = case.guide_state or {}
        if saved.get("initial_days"):
            return {}
        baseline = [day.model_dump() for day in build_draft_itinerary(DraftPlanInput(
            destination=row.destination, destination_scope=row.destination_scope,
            duration_days=row.duration_days, attractions=row.attractions, travel_pace=row.travel_pace,
            interest_tags=infer_interest_tags(case.original_request)))]
        allowed = list(dict.fromkeys([*row.attractions, *ATTRACTION_CATALOG.get(row.destination or "", {}),
                                      *ATTRACTIONS.get(row.destination or "", {})]))
        context = {"destination": row.destination, "travel_pace": row.travel_pace,
                   "traveler_count": row.traveler_count, "budget": str(row.budget),
                   "currency": row.currency, "elevator_required": bool(row.hard_constraints.get("elevator_required")),
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
        previous = case.guide_state or {}
        if not previous.get("initial_days"):
            case.guide_state = {**previous, "initial_days": days, "itinerary_source": source,
                                "itinerary_version": 1, "itinerary_model_trace": trace,
                                "itinerary_error": error}
            add_event(session, case.id, "Travel Planner", "ITINERARY_GENERATED" if not error else "ITINERARY_MODEL_FAILED",
                      case.status, {"source": source, "version": 1, "error_type": error})
    return {}


def discovery_worker(state: FlowState) -> FlowState:
    with SessionLocal.begin() as session:
        case = session.get(Case, state["case_id"], with_for_update=True)
        req = session.scalar(select(Requirement).where(Requirement.case_id == case.id))
        catalog = search_suppliers(_requirements_from_row(req))
        for item in catalog:
            exists = session.scalar(select(Offer).where(Offer.case_id == case.id,
                                                        Offer.catalog_product_id == item.product_id,
                                                        Offer.version == 1))
            if not exists:
                session.add(Offer(case_id=case.id, catalog_product_id=item.product_id, version=1,
                                  total_amount=item.total_amount, currency=item.currency,
                                  includes=item.includes, supplier_claims=item.claims,
                                  expires_at=item.expires_at))
        session.flush()
        review_offer = session.scalar(select(Offer).where(Offer.case_id == case.id,
                                                           Offer.catalog_product_id == "PACKAGE_C"))
        if review_offer and not session.scalar(select(OfferAssessment).where(OfferAssessment.offer_id == review_offer.id)):
            sources, assessment = verify_evidence("PACKAGE_C", bool(req.hard_constraints.get("elevator_required")))
            for source in sources:
                session.add(Evidence(offer_id=review_offer.id, claim_type=source.claim_type, source=source.source,
                                     polarity=source.polarity, source_strength=source.strength,
                                     source_reference=source.reference, detail=source.detail))
            session.add(OfferAssessment(offer_id=review_offer.id, claim_type="lift_serves_all_guest_floors",
                                        verdict=assessment.verdict, reason_code=assessment.reason_code,
                                        assessment_version=1, source_refs=assessment.source_refs))
        set_status(session, case, "OFFERS_DISCOVERED", "discovery_worker", "Comparison Worker",
                   "SUPPLIERS_DISCOVERED", {"count": len(catalog), "synthetic": True})
    return {"excluded_ids": state.get("excluded_ids", []), "rerank_count": state.get("rerank_count", 0)}


def comparison_worker(state: FlowState) -> FlowState:
    with SessionLocal.begin() as session:
        case = session.get(Case, state["case_id"], with_for_update=True)
        req = session.scalar(select(Requirement).where(Requirement.case_id == case.id))
        offers = session.scalars(select(Offer).where(Offer.case_id == case.id)).all()
        inputs = RankingInput(budget=Decimal(req.budget), currency=req.currency,
                              offers=[{"product_id": o.catalog_product_id, "total_amount": o.total_amount,
                                       "currency": o.currency, "includes": o.includes,
                                       "claims": o.supplier_claims, "expires_at": o.expires_at} for o in offers],
                              excluded_ids=state.get("excluded_ids", []))
        if state.get("rerank_count", 0):
            verdicts = {o.catalog_product_id: a.verdict for o in offers for a in
                        session.scalars(select(OfferAssessment).where(OfferAssessment.offer_id == o.id)).all()}
            ranked = rerank_offers(inputs, verdicts).ordered_product_ids
        else:
            ranked = compare_offers(inputs).ordered_product_ids
        candidate = next((o for product in ranked for o in offers if o.catalog_product_id == product), None)
        set_status(session, case, "EVIDENCE_REVIEW" if candidate else "HUMAN_REVIEW", "comparison_worker",
                   "Comparison Worker", "OFFERS_RANKED", {"ordered_products": ranked,
                                                           "rerank_count": state.get("rerank_count", 0)})
        return {"candidate_id": candidate.id if candidate else ""}


def route_candidate(state: FlowState) -> str:
    return "evidence" if state.get("candidate_id") else "human_review"


def evidence_worker(state: FlowState) -> FlowState:
    with SessionLocal.begin() as session:
        case = session.get(Case, state["case_id"], with_for_update=True)
        req = session.scalar(select(Requirement).where(Requirement.case_id == case.id))
        offer = session.get(Offer, state["candidate_id"])
        sources, assessment = verify_evidence(offer.catalog_product_id,
                                               bool(req.hard_constraints.get("elevator_required")))
        existing = session.scalar(select(OfferAssessment).where(OfferAssessment.offer_id == offer.id,
                                                                 OfferAssessment.claim_type == "lift_serves_all_guest_floors"))
        if not existing:
            for source in sources:
                session.add(Evidence(offer_id=offer.id, claim_type=source.claim_type, source=source.source,
                                     polarity=source.polarity, source_strength=source.strength,
                                     source_reference=source.reference, detail=source.detail))
            session.add(OfferAssessment(offer_id=offer.id, claim_type="lift_serves_all_guest_floors",
                                        verdict=assessment.verdict, reason_code=assessment.reason_code,
                                        assessment_version=1, source_refs=assessment.source_refs))
        set_status(session, case, "EVIDENCE_REVIEW", "evidence_worker", "Evidence Worker",
                   "EVIDENCE_ASSESSED", {"offer_id": offer.id, "product_id": offer.catalog_product_id,
                                         "verdict": assessment.verdict, "reason": assessment.reason_code,
                                         "source_refs": assessment.source_refs})
        return {"verdict": assessment.verdict}


def manager_worker(state: FlowState) -> FlowState:
    with SessionLocal.begin() as session:
        case = session.get(Case, state["case_id"], with_for_update=True)
        if state["verdict"] == "PASS":
            set_status(session, case, "OFFERS_VERIFIED", "manager_worker", "Manager", "OFFER_VERIFIED",
                       {"offer_id": state["candidate_id"]})
            return {"final_offer_id": state["candidate_id"], "should_rerank": False}
        excluded = list(dict.fromkeys([*state.get("excluded_ids", []),
                                       session.get(Offer, state["candidate_id"]).catalog_product_id]))
        rerank_count = state.get("rerank_count", 0)
        if rerank_count < settings.max_reranks:
            rerank_count += 1
            set_status(session, case, "EVIDENCE_CONFLICT", "manager_worker", "Manager", "MANAGER_RERANK",
                       {"excluded_products": excluded, "reason": state["verdict"], "rerank_count": rerank_count})
        else:
            set_status(session, case, "HUMAN_REVIEW", "manager_worker", "Manager", "NO_PASS_CANDIDATE",
                       {"excluded_products": excluded, "reason": state["verdict"]})
        return {"excluded_ids": excluded, "rerank_count": rerank_count,
                "should_rerank": rerank_count > state.get("rerank_count", 0)}


def route_manager(state: FlowState) -> str:
    if state.get("verdict") == "PASS":
        return "prepare_approval"
    return "comparison" if state.get("should_rerank") else "human_review"


def approval_worker(state: FlowState) -> FlowState:
    with SessionLocal() as session:
        offer = session.get(Offer, state["final_offer_id"])
        data = ApprovalInput(case_id=state["case_id"], offer_id=offer.id, offer_version=offer.version,
                             amount=offer.total_amount, currency=offer.currency, expires_at=offer.expires_at)
    approval = prepare_approval(data)
    return {"approval_id": approval.id}


def wait_approval(state: FlowState) -> FlowState:
    interrupt({"type": "approval", "approval_id": state["approval_id"]})
    return {}


def route_decision(state: FlowState) -> str:
    with SessionLocal() as session:
        approval = session.get(Approval, state["approval_id"])
        if approval.status == "APPROVED":
            return "booking"
        if approval.status == "REJECTED":
            return "rejected"
        return "human_review"


def booking_worker(state: FlowState) -> FlowState:
    order = execute_mock_booking(BookingInput(case_id=state["case_id"], approval_id=state["approval_id"],
                                             offer_id=state["final_offer_id"],
                                             idempotency_key=f"mock-booking:{state['approval_id']}"))
    return {"order_id": order.id}


def review_worker(state: FlowState) -> FlowState:
    summary = generate_review(ReviewInput(case_id=state["case_id"], order_id=state["order_id"],
                                          offer_id=state["final_offer_id"]))
    with SessionLocal.begin() as session:
        case = session.get(Case, state["case_id"], with_for_update=True)
        order = session.get(Order, state["order_id"])
        if not order or order.case_id != case.id:
            raise RuntimeError("Order read-back mismatch")
        if case.status != "DEMO_COMPLETED":
            set_status(session, case, "DEMO_COMPLETED", "review_worker", "Review Worker", "REVIEW_COMPLETED",
                       {"summary": summary.summary, "order_id": order.id})
    return {}


def rejected_worker(state: FlowState) -> FlowState:
    with SessionLocal.begin() as session:
        case = session.get(Case, state["case_id"], with_for_update=True)
        add_event(session, case.id, "Review Worker", "CASE_REJECTED", "REJECTED", {})
    return {}


def human_review_worker(state: FlowState) -> FlowState:
    with SessionLocal.begin() as session:
        case = session.get(Case, state["case_id"], with_for_update=True)
        if case.status != "HUMAN_REVIEW":
            set_status(session, case, "HUMAN_REVIEW", "human_review", "Manager", "HUMAN_REVIEW_REQUIRED", {})
        else:
            add_event(session, case.id, "Manager", "HUMAN_REVIEW_REQUIRED", "HUMAN_REVIEW", {})
    return {}


def build_graph(checkpointer):
    graph = StateGraph(FlowState)
    for name, node in {
        "requirements": requirements_worker, "wait_clarification": wait_clarification,
        "itinerary": itinerary_worker,
        "discovery": discovery_worker, "comparison": comparison_worker,
        "evidence": evidence_worker, "manager": manager_worker,
        "prepare_approval": approval_worker, "wait_approval": wait_approval,
        "booking": booking_worker, "review": review_worker,
        "rejected": rejected_worker, "human_review": human_review_worker,
    }.items():
        graph.add_node(name, node)
    graph.add_edge(START, "requirements")
    graph.add_conditional_edges("requirements", route_requirements)
    graph.add_edge("wait_clarification", "requirements")
    graph.add_edge("itinerary", "discovery")
    graph.add_edge("discovery", "comparison")
    graph.add_conditional_edges("comparison", route_candidate)
    graph.add_edge("evidence", "manager")
    graph.add_conditional_edges("manager", route_manager)
    graph.add_edge("prepare_approval", "wait_approval")
    graph.add_conditional_edges("wait_approval", route_decision)
    graph.add_edge("booking", "review")
    for terminal in ("review", "rejected", "human_review"):
        graph.add_edge(terminal, END)
    return graph.compile(checkpointer=checkpointer)
