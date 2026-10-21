"""Reads and writes for a Case's guide data: conversation, itinerary versions and revision proposals.

All functions take the caller's session so they join the caller's transaction.
"""

from datetime import datetime, timezone

from sqlalchemy import func, select, update

from app.db import ConversationTurn, ItineraryProposal, ItineraryVersion, Requirement
from app.skills.contracts import DraftPlanInput
from app.skills.domain import build_draft_itinerary, infer_interest_tags

CONVERSATION_WINDOW = 30


# Needs that may shape an outline and be sent to a planning model: no medical notes, contacts or diets.
MOBILITY_NEEDS = ("wheelchair", "max_walk_meters", "step_free")


def access_needs(requirement: Requirement | None) -> dict:
    needs = requirement.hard_constraints.get("needs", {}) if requirement else {}
    return {key: needs[key] for key in MOBILITY_NEEDS if needs.get(key) not in (None, False, "NONE")}


def draft_days(requirement: Requirement, language: str = "en", request: str = "") -> list[dict]:
    """The rule-based outline for a Case: the first version, and the preview until a version is stored."""
    return [day.model_dump() for day in build_draft_itinerary(DraftPlanInput(
        destination=requirement.destination, destination_scope=requirement.destination_scope,
        duration_days=requirement.duration_days, attractions=requirement.attractions,
        travel_pace=requirement.travel_pace, interest_tags=infer_interest_tags(request), language=language,
        access_needs=access_needs(requirement)))]


def current_itinerary(session, case_id: str) -> ItineraryVersion | None:
    return session.scalar(select(ItineraryVersion).where(ItineraryVersion.case_id == case_id)
                          .order_by(ItineraryVersion.version.desc()).limit(1))


def add_itinerary_version(session, case_id: str, days: list[dict], source: str, *, model_trace: dict | None = None,
                          error: str | None = None, proposal_id: str | None = None,
                          only_if_first: bool = False) -> int | None:
    """Append the next version. With only_if_first, do nothing when an outline already exists."""
    latest = session.scalar(select(func.max(ItineraryVersion.version)).where(ItineraryVersion.case_id == case_id))
    if only_if_first and latest:
        return None
    version = (latest or 0) + 1
    session.add(ItineraryVersion(case_id=case_id, version=version, days=days, source=source,
                                 model_trace=model_trace, error=error, proposal_id=proposal_id))
    return version


def conversation(session, case_id: str) -> list[dict]:
    rows = session.scalars(select(ConversationTurn).where(ConversationTurn.case_id == case_id)
                           .order_by(ConversationTurn.id.desc()).limit(CONVERSATION_WINDOW)).all()
    return [{"role": row.role, "text": row.text, "source": row.source, "created_at": row.created_at.isoformat()}
            for row in reversed(rows)]


def traveler_turns(session, case_id: str) -> list[str]:
    return list(session.scalars(select(ConversationTurn.text).where(ConversationTurn.case_id == case_id,
                                                                     ConversationTurn.role == "traveler")
                                .order_by(ConversationTurn.id)).all())


def add_turn(session, case_id: str, role: str, text: str, source: str) -> None:
    session.add(ConversationTurn(case_id=case_id, role=role, source=source, text=text[:1000]))


def latest_proposal(session, case_id: str) -> ItineraryProposal | None:
    return session.scalar(select(ItineraryProposal).where(ItineraryProposal.case_id == case_id)
                          .order_by(ItineraryProposal.created_at.desc()).limit(1))


def proposal_payload(proposal: ItineraryProposal | None) -> dict | None:
    if not proposal:
        return None
    return {"id": proposal.id, "request": proposal.request, "status": proposal.status, "days": proposal.days,
            "scope": "ILLUSTRATIVE_ONLY", "model_trace": proposal.model_trace}


def propose(session, case_id: str, proposal_id: str, request: str, days: list[dict], model_trace: dict | None) -> None:
    """A new proposal replaces any pending one (the traveler only ever reviews the latest)."""
    session.execute(update(ItineraryProposal).where(ItineraryProposal.case_id == case_id,
                                                    ItineraryProposal.status == "PENDING")
                    .values(status="SUPERSEDED", decided_at=datetime.now(timezone.utc)))
    session.flush()
    session.add(ItineraryProposal(id=proposal_id, case_id=case_id, request=request, status="PENDING",
                                  days=days, model_trace=model_trace))


EDITABLE_DAY_FIELDS = ("title", "note", "activities", "rest_note")


def edit_itinerary(session, case_id: str, base_version: int, edits: list[dict], editor_id: str) -> int:
    """Save the traveler's own wording as the next version. Fails if someone saved a newer version meanwhile."""
    current = current_itinerary(session, case_id)
    if not current:
        raise LookupError("NO_ITINERARY")
    if current.version != base_version:
        raise ValueError("ITINERARY_CHANGED")
    by_day = {edit["day_number"]: edit for edit in edits}
    if set(by_day) != {day["day_number"] for day in current.days}:
        raise ValueError("DAYS_MISMATCH")
    days = [{**day, **{field: by_day[day["day_number"]][field] for field in EDITABLE_DAY_FIELDS}} for day in current.days]
    if days == current.days:
        return current.version
    # A pending suggestion was written against the old outline, so it no longer applies.
    session.execute(update(ItineraryProposal).where(ItineraryProposal.case_id == case_id,
                                                    ItineraryProposal.status == "PENDING")
                    .values(status="SUPERSEDED", decided_at=datetime.now(timezone.utc)))
    return add_itinerary_version(session, case_id, days, "TRAVELER_EDITED", model_trace={"edited_by": editor_id})
