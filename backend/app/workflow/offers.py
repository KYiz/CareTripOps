"""Offer nodes: supplier discovery, ranking, evidence, Manager arbitration and advisor review."""

import hashlib
from decimal import Decimal

from langgraph.types import interrupt
from sqlalchemy import select

from app import notify
from app.config import settings
from app.db import (Case, Evidence, Offer, OfferAssessment, OfferRanking, Requirement, ReviewTask, SessionLocal,
                    latest_claims, offer_verdict, set_status)
from app.skills.contracts import RankingInput
from app.skills.domain import assess_offer, compare_offers, required_claims, rerank_offers, search_suppliers
from app.suppliers import get_supplier
from app.workflow.state import FlowState, requirements_from_row


def _ranking_input(req: Requirement, offers: list[Offer], excluded: list[str]) -> RankingInput:
    return RankingInput(budget=Decimal(req.budget), currency=req.currency, excluded_ids=excluded,
                        elevator_required=bool(req.hard_constraints.get("elevator_required")),
                        needs=req.hard_constraints.get("needs", {}), travel_pace=req.travel_pace,
                        offers=[{"product_id": o.catalog_product_id, "total_amount": o.total_amount,
                                 "currency": o.currency, "includes": o.includes, "claims": o.supplier_claims,
                                 "expires_at": o.expires_at, "attributes": o.attributes,
                                 "cancellation_policy": o.cancellation_policy} for o in offers])


def _request_reviews(session, case: Case, req: Requirement) -> int:
    """No offer passed: ask an advisor about affordable offers whose evidence was inconclusive.
    Reviews are only opened when they can unblock the trip, so the queue never fills with moot ones."""
    opened = 0
    for offer in session.scalars(select(Offer).where(Offer.case_id == case.id, Offer.total_amount <= req.budget)).all():
        # Only offers whose every claim is either proven or open to review: a blocked claim cannot be reviewed away.
        if offer_verdict(session, offer.id).verdict != "REVIEW":
            continue
        for claim in latest_claims(session, offer.id).values():
            if claim.verdict != "REVIEW":
                continue
            if not session.scalar(select(ReviewTask).where(ReviewTask.offer_id == offer.id, ReviewTask.status == "OPEN",
                                                           ReviewTask.claim_type == claim.claim_type)):
                session.add(ReviewTask(case_id=case.id, offer_id=offer.id, claim_type=claim.claim_type,
                                       reason_code=claim.reason_code))
                notify.queue_for_advisors(session, case, "REVIEW_NEEDED",
                                          {"case_short": case.id[:8], "product": offer.name or offer.catalog_product_id})
            opened += 1
    return opened


def discovery_worker(state: FlowState) -> FlowState:
    """Fetch supplier offers, store immutable snapshots with their evidence, and assess every offer."""
    with SessionLocal() as session:
        req = session.scalar(select(Requirement).where(Requirement.case_id == state["case_id"]))
        requirements = requirements_from_row(req)
        claims = required_claims(bool(req.hard_constraints.get("elevator_required")), req.hard_constraints.get("needs"))
    catalog = search_suppliers(requirements, get_supplier())  # Network call: no transaction held.
    with SessionLocal.begin() as session:
        case = session.get(Case, state["case_id"], with_for_update=True)
        for item in catalog:
            offer = session.scalar(select(Offer).where(Offer.case_id == case.id, Offer.catalog_product_id == item.product_id,
                                                       Offer.version == 1))
            if offer:
                continue  # Replayed step: snapshots never change.
            offer = Offer(case_id=case.id, catalog_product_id=item.product_id, version=1, supplier="simulator",
                          supplier_offer_ref=item.supplier_offer_ref, name=item.name, attributes=item.attributes,
                          cancellation_policy=item.cancellation_policy, total_amount=item.total_amount,
                          currency=item.currency, includes=item.includes, supplier_claims=item.claims,
                          expires_at=item.expires_at)
            session.add(offer)
            session.flush()
            for source in item.evidence:
                session.add(Evidence(offer_id=offer.id, claim_type=source.claim_type, source=source.source,
                                     polarity=source.polarity, source_strength=source.strength,
                                     source_reference=source.reference, detail=source.detail, source_url=source.url,
                                     content_hash=hashlib.sha256(source.detail.encode()).hexdigest()))
            for claim, assessment in assess_offer(item.evidence, claims).items():
                session.add(OfferAssessment(offer_id=offer.id, claim_type=claim, verdict=assessment.verdict,
                                            reason_code=assessment.reason_code, assessment_version=1,
                                            source_refs=assessment.source_refs))
        set_status(session, case, "OFFERS_DISCOVERED", "discovery_worker", "Comparison Worker",
                   "SUPPLIERS_DISCOVERED", {"count": len(catalog), "supplier": "simulator"})
    return {"excluded_ids": state.get("excluded_ids", []), "rerank_count": state.get("rerank_count", 0)}


def comparison_worker(state: FlowState) -> FlowState:
    """Rank on supplier-stated features; once verdicts are known (after a rerank or a review), exclude
    offers that failed or could not settle verification."""
    rank_round = state.get("rank_round", 0) + 1
    with SessionLocal.begin() as session:
        case = session.get(Case, state["case_id"], with_for_update=True)
        req = session.scalar(select(Requirement).where(Requirement.case_id == case.id))
        offers = session.scalars(select(Offer).where(Offer.case_id == case.id)).all()
        inputs = _ranking_input(req, offers, state.get("excluded_ids", []))
        if state.get("rerank_count", 0) or state.get("reviewed"):
            verdicts = {o.catalog_product_id: offer_verdict(session, o.id).verdict for o in offers}
            result = rerank_offers(inputs, verdicts)
        else:
            result = compare_offers(inputs)
        by_product = {o.catalog_product_id: o for o in offers}
        for item in result.ranked:
            if not session.scalar(select(OfferRanking).where(OfferRanking.offer_id == by_product[item.product_id].id,
                                                             OfferRanking.rank_round == rank_round)):
                session.add(OfferRanking(offer_id=by_product[item.product_id].id, rank_round=rank_round,
                                         eligible=item.eligible, score=item.score, factors=item.factors))
        ranked = result.ordered_product_ids
        candidate = by_product[ranked[0]] if ranked else None
        reviews = 0 if candidate else _request_reviews(session, case, req)
        status = "EVIDENCE_REVIEW" if candidate else "AWAITING_REVIEW" if reviews else "HUMAN_REVIEW"
        set_status(session, case, status, "comparison_worker", "Comparison Worker", "OFFERS_RANKED",
                   {"ordered_products": ranked, "rerank_count": state.get("rerank_count", 0), "round": rank_round,
                    "scores": {item.product_id: item.score for item in result.ranked}})
        return {"candidate_id": candidate.id if candidate else "", "rank_round": rank_round, "open_reviews": reviews}


def route_candidate(state: FlowState) -> str:
    if state.get("candidate_id"):
        return "evidence"
    return "wait_review" if state.get("open_reviews") else "human_review"


def evidence_worker(state: FlowState) -> FlowState:
    with SessionLocal.begin() as session:
        case = session.get(Case, state["case_id"], with_for_update=True)
        offer = session.get(Offer, state["candidate_id"])
        assessment = offer_verdict(session, offer.id)
        set_status(session, case, "EVIDENCE_REVIEW", "evidence_worker", "Evidence Worker",
                   "EVIDENCE_ASSESSED", {"offer_id": offer.id, "product_id": offer.catalog_product_id,
                                         "verdict": assessment.verdict, "reason": assessment.reason_code,
                                         "version": assessment.assessment_version,
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
        reviews = 0
        if rerank_count < settings.max_reranks:
            rerank_count += 1
            set_status(session, case, "EVIDENCE_CONFLICT", "manager_worker", "Manager", "MANAGER_RERANK",
                       {"excluded_products": excluded, "reason": state["verdict"], "rerank_count": rerank_count})
        else:
            reviews = _request_reviews(session, case, session.scalar(select(Requirement).where(Requirement.case_id == case.id)))
            set_status(session, case, "AWAITING_REVIEW" if reviews else "HUMAN_REVIEW", "manager_worker", "Manager",
                       "NO_PASS_CANDIDATE", {"excluded_products": excluded, "reason": state["verdict"],
                                             "open_reviews": reviews})
        return {"excluded_ids": excluded, "rerank_count": rerank_count, "open_reviews": reviews,
                "should_rerank": rerank_count > state.get("rerank_count", 0)}


def route_manager(state: FlowState) -> str:
    if state.get("verdict") == "PASS":
        return "prepare_approval"
    if state.get("should_rerank"):
        return "comparison"
    return "wait_review" if state.get("open_reviews") else "human_review"


def wait_review(state: FlowState) -> FlowState:
    """Pause until an advisor settles the inconclusive evidence; then rank again with their verdicts."""
    interrupt({"type": "review"})
    # Earlier exclusions were provisional; from here the latest verdicts (incl. the advisor's) decide.
    return {"reviewed": True, "excluded_ids": []}

