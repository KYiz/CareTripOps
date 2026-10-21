import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select

from app.db import Approval, Case, Offer, SessionLocal, offer_verdict, set_status
from app.config import settings
from app.jobs import enqueue
from app.skills.contracts import ApprovalInput


def demo_nonce(approval_id: str) -> str:
    return hmac.new(settings.demo_nonce_secret.encode(), approval_id.encode(), hashlib.sha256).hexdigest()


def prepare_approval(data: ApprovalInput) -> Approval:
    """Persist one matching pending approval before the graph reaches interrupt."""
    with SessionLocal.begin() as session:
        case = session.get(Case, data.case_id, with_for_update=True)
        offer = session.get(Offer, data.offer_id)
        if not case or not offer or offer.case_id != data.case_id:
            raise ValueError("Case and offer mismatch")
        if (offer.version != data.offer_version or Decimal(offer.total_amount) != data.amount
                or offer.currency != data.currency or offer.expires_at <= datetime.now(timezone.utc)):
            raise ValueError("Offer snapshot is stale")
        assessment = offer_verdict(session, offer.id)
        if not assessment or assessment.verdict != "PASS":
            raise ValueError("A final PASS assessment is required")
        existing = session.scalar(select(Approval).where(Approval.case_id == data.case_id, Approval.status == "PENDING"))
        if existing:
            if existing.offer_id != data.offer_id:
                raise ValueError("A different approval is already pending")
            if case.status == "RECOVERY_REQUIRED":
                set_status(session, case, "AWAITING_APPROVAL", "wait_approval", "Manager", "APPROVAL_RECOVERED",
                           {"approval_id": existing.id})
                existing.case_state_version = case.state_version
            elif case.status != "AWAITING_APPROVAL":
                raise ValueError("Case is not in an approvable state")
            session.flush()
            session.expunge(existing)
            return existing
        if case.status != "OFFERS_VERIFIED":
            raise ValueError("Case is not verified for approval")
        approval_id = str(uuid4())
        nonce = demo_nonce(approval_id)
        set_status(session, case, "AWAITING_APPROVAL", "wait_approval", "Manager", "APPROVAL_PREPARED",
                   {"offer_id": offer.id, "amount": str(offer.total_amount), "currency": offer.currency})
        approval = Approval(id=approval_id, case_id=case.id, offer_id=offer.id, offer_version=offer.version,
                            approved_amount=offer.total_amount, currency=offer.currency,
                            case_state_version=case.state_version, nonce_hash=hashlib.sha256(nonce.encode()).hexdigest())
        session.add(approval)
        session.flush()
        session.expunge(approval)
        return approval


def decide_approval(case_id: str, approval_id: str, decision: str, nonce: str, expected_version: int) -> tuple[str, bool]:
    stale = False
    with SessionLocal.begin() as session:
        case = session.get(Case, case_id, with_for_update=True)
        approval = session.get(Approval, approval_id, with_for_update=True)
        if not case or not approval or approval.case_id != case_id:
            raise ValueError("Unknown case approval")
        if not secrets.compare_digest(approval.nonce_hash, hashlib.sha256(nonce.encode()).hexdigest()):
            raise ValueError("Invalid approval nonce")
        target = "APPROVED" if decision == "APPROVE" else "REJECTED"
        if approval.status == target:
            return target, False
        if approval.status != "PENDING" or case.status != "AWAITING_APPROVAL":
            raise ValueError("Approval is no longer pending")
        offer = session.get(Offer, approval.offer_id)
        assessment = offer_verdict(session, approval.offer_id)
        if (case.state_version != expected_version or approval.case_state_version != expected_version
                or not offer or offer.case_id != case_id or approval.offer_version != offer.version
                or Decimal(approval.approved_amount) != Decimal(offer.total_amount)
                or approval.currency != offer.currency or offer.expires_at <= datetime.now(timezone.utc)
                or not assessment or assessment.verdict != "PASS"):
            approval.status = "EXPIRED"
            set_status(session, case, "HUMAN_REVIEW", "approval_decision", "Manager", "STALE_APPROVAL",
                       {"approval_id": approval.id})
            stale = True
        else:
            approval.status = target
            approval.decided_at = datetime.now(timezone.utc)
            set_status(session, case, target, "approval_decision", "Manager", "APPROVAL_DECIDED",
                       {"approval_id": approval.id, "decision": target})
            # Committed with the decision: either both happen or neither does.
            enqueue(session, case_id, "resume")
    if stale:
        raise ValueError("STALE_OFFER")
    return target, True
