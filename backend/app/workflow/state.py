"""Workflow state shared by every node."""

from typing import TypedDict

from sqlalchemy import select

from app.db import CaseMember, Requirement, TravelerProfile, User
from app.skills.contracts import RequirementOutput


class FlowState(TypedDict, total=False):
    case_id: str
    candidate_id: str
    excluded_ids: list[str]
    rerank_count: int
    verdict: str
    final_offer_id: str
    approval_id: str
    order_id: str
    payment_status: str
    order_status: str
    rank_round: int
    open_reviews: int
    reviewed: bool
    missing_fields: list[str]
    should_rerank: bool
    model_error: bool
    unsupported_destination: bool



# Needs that shape search and ranking. Medical notes and the emergency contact never leave the profile.
PLANNING_NEEDS = ("wheelchair", "max_walk_meters", "step_free", "accessible_bathroom", "dietary")


def owner_needs(session, case_id: str) -> dict:
    """The trip owner's saved needs, if they consented to storing them; snapshotted onto the Case."""
    row = session.execute(select(TravelerProfile, User.sensitive_consent_at)
                          .join(CaseMember, CaseMember.user_id == TravelerProfile.user_id)
                          .join(User, User.id == TravelerProfile.user_id)
                          .where(CaseMember.case_id == case_id, CaseMember.role == "OWNER")).first()
    if not row or not row.sensitive_consent_at:
        return {}
    return {key: row.TravelerProfile.needs[key] for key in PLANNING_NEEDS if key in row.TravelerProfile.needs}


def requirements_from_row(row: Requirement) -> RequirementOutput:
    return RequirementOutput(destination=row.destination, destination_scope=row.destination_scope,
                             attractions=row.attractions, travel_pace=row.travel_pace,
                             departure_date=row.departure_date,
                             traveler_count=row.traveler_count, duration_days=row.duration_days,
                             budget=row.budget, currency=row.currency,
                             elevator_required=bool(row.hard_constraints.get("elevator_required")),
                             missing_fields=row.missing_fields)

