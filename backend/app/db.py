"""Database access: the session factory, every model, and small helpers shared by workflow code.

Models are defined by domain in app/models/; they are re-exported here so callers import from one place.
"""

from dataclasses import dataclass

from sqlalchemy import select

from app.database import Base, SessionLocal, engine, utcnow
from app.models.accounts import CaseInvitation, CaseMember, LoginCode, TravelerProfile, User, UserSession
from app.models.cases import (AuditEvent, Case, ConversationTurn, ItineraryProposal, ItineraryVersion,
                              Requirement)
from app.models.offers import Evidence, Offer, OfferAssessment, OfferRanking, ReviewTask
from app.models.ops import CaseNote, HelpRequest, Job, Notification
from app.models.orders import Approval, Order, Payment, PaymentEvent

__all__ = ["Base", "SessionLocal", "engine", "utcnow", "CaseInvitation", "CaseMember", "LoginCode", "TravelerProfile",
           "User", "UserSession", "AuditEvent", "Case", "ConversationTurn", "ItineraryProposal", "ItineraryVersion", "Requirement", "Evidence",
           "Offer", "OfferAssessment", "OfferRanking", "ReviewTask", "CaseNote", "HelpRequest", "Job", "Notification", "Approval", "Order", "Payment",
           "PaymentEvent", "OfferVerdict", "latest_claims", "offer_verdict", "add_event", "set_status"]


SEVERITY = {"BLOCK": 0, "REVIEW": 1, "PASS": 2}


@dataclass(frozen=True)
class OfferVerdict:
    """An offer's standing across every claim the traveler needs: the weakest claim decides."""
    verdict: str
    reason_code: str
    claim_type: str
    assessment_version: int
    source_refs: list
    claims: dict


def latest_claims(session, offer_id: str) -> "dict[str, OfferAssessment]":
    """The newest assessment of each claim; advisor decisions add newer versions."""
    latest: dict = {}
    for row in session.scalars(select(OfferAssessment).where(OfferAssessment.offer_id == offer_id)
                               .order_by(OfferAssessment.assessment_version.desc())):
        latest.setdefault(row.claim_type, row)
    return latest


def offer_verdict(session, offer_id: str) -> OfferVerdict | None:
    claims = latest_claims(session, offer_id)
    if not claims:
        return None
    decisive = min(claims.values(), key=lambda row: (SEVERITY[row.verdict], row.claim_type))
    refs = list(dict.fromkeys(ref for row in claims.values() for ref in row.source_refs))
    return OfferVerdict(decisive.verdict, decisive.reason_code, decisive.claim_type,
                        max(row.assessment_version for row in claims.values()), refs, claims)


def add_event(session, case_id: str, agent: str, event_type: str, status: str, payload: dict | None = None):
    session.add(AuditEvent(case_id=case_id, agent_name=agent, event_type=event_type, status=status, payload=payload or {}))


def set_status(session, case: Case, status: str, node: str, agent: str, event_type: str, payload: dict | None = None):
    case.status = status
    case.active_node = node
    case.state_version += 1
    add_event(session, case.id, agent, event_type, status, payload)

