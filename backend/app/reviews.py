"""The advisor queue for offers whose evidence could not settle a traveler's hard requirement."""

from datetime import datetime, timezone

from sqlalchemy import func, select

from app import jobs
from app.db import (Case, Evidence, Offer, OfferAssessment, Requirement, ReviewTask, SessionLocal, User, add_event,
                    latest_claims)
from app.errors import fail


def open_reviews() -> list[dict]:
    with SessionLocal() as session:
        rows = session.execute(select(ReviewTask, Offer, Case).join(Offer, Offer.id == ReviewTask.offer_id)
                               .join(Case, Case.id == ReviewTask.case_id)
                               # Only reviews a trip is actually waiting on.
                               .where(ReviewTask.status == "OPEN", Case.status == "AWAITING_REVIEW")
                               .order_by(ReviewTask.created_at)).all()
        result = []
        for task, offer, case in rows:
            destination = session.scalar(select(Requirement.destination).where(Requirement.case_id == case.id))
            evidence = session.scalars(select(Evidence).where(Evidence.offer_id == offer.id,
                                                              Evidence.claim_type == task.claim_type)
                                       .order_by(Evidence.source_time, Evidence.source_reference)).all()
            result.append({
                "id": task.id, "case_id": case.id, "case_status": case.status, "destination": destination,
                "claim_type": task.claim_type, "reason_code": task.reason_code, "created_at": task.created_at.isoformat(),
                "offer": {"id": offer.id, "product_id": offer.catalog_product_id, "name": offer.name,
                          "total_amount": f"{offer.total_amount:.2f}", "currency": offer.currency,
                          "attributes": offer.attributes},
                "evidence": [{"source": e.source, "polarity": e.polarity, "strength": e.source_strength,
                              "reference": e.source_reference, "detail": e.detail, "url": e.source_url}
                             for e in evidence],
            })
        return result


def resolve(task_id: str, advisor: User, decision: str, note: str) -> dict:
    """Record the advisor's verdict as a new assessment version and resume a Case waiting on it."""
    if decision not in {"PASS", "BLOCK"}:
        fail("INVALID_DECISION", "Decision must be PASS or BLOCK", 400)
    with SessionLocal.begin() as session:
        task = session.get(ReviewTask, task_id, with_for_update=True)
        if not task:
            fail("REVIEW_NOT_FOUND", "Review task not found", 404)
        if task.status != "OPEN":
            fail("REVIEW_ALREADY_RESOLVED", "This review was already resolved")
        task.status = f"RESOLVED_{decision}"
        task.resolution_note, task.resolved_by = note.strip()[:2000], advisor.id
        task.resolved_at = datetime.now(timezone.utc)
        previous = latest_claims(session, task.offer_id).get(task.claim_type)
        session.add(OfferAssessment(
            offer_id=task.offer_id, claim_type=task.claim_type, verdict=decision,
            reason_code="ADVISOR_CONFIRMED" if decision == "PASS" else "ADVISOR_REJECTED",
            assessment_version=(previous.assessment_version if previous else 0) + 1,
            source_refs=[*(previous.source_refs if previous else []), f"ADVISOR-{task.id[:8]}"]))
        case = session.get(Case, task.case_id, with_for_update=True)
        add_event(session, case.id, "Travel Advisor", "EVIDENCE_REVIEWED", case.status,
                  {"offer_id": task.offer_id, "decision": decision})
        remaining = session.scalar(select(func.count()).select_from(ReviewTask)
                                   .where(ReviewTask.case_id == case.id, ReviewTask.status == "OPEN"))
        resumed = False
        if case.status == "AWAITING_REVIEW" and not remaining:
            jobs.enqueue(session, case.id, "resume")
            resumed = True
        return {"id": task_id, "status": task.status, "case_resumed": resumed}
