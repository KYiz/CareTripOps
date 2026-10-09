import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select

from app.db import Approval, Case, Offer, OfferAssessment, Order, SessionLocal, set_status
from app.config import settings
from app.skills.contracts import ApprovalInput, BookingInput


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
        assessment = session.scalar(select(OfferAssessment).where(OfferAssessment.offer_id == offer.id))
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


def execute_mock_booking(data: BookingInput) -> Order:
    """Commit and read back the one simulated order for an approved snapshot."""
    with SessionLocal.begin() as session:
        case = session.get(Case, data.case_id, with_for_update=True)
        approval = session.get(Approval, data.approval_id, with_for_update=True)
        offer = session.get(Offer, data.offer_id)
        existing = session.scalar(select(Order).where(Order.idempotency_key == data.idempotency_key))
        if existing:
            if (existing.case_id != data.case_id or existing.approval_id != data.approval_id
                    or existing.offer_id != data.offer_id):
                raise ValueError("Idempotency key belongs to another booking")
            order_id = existing.id
        else:
            if not approval or not case or not offer or approval.status != "APPROVED":
                raise ValueError("Approved case, approval, and offer are required")
            if (approval.case_id != case.id or approval.offer_id != offer.id or offer.case_id != case.id
                    or approval.offer_version != offer.version or Decimal(approval.approved_amount) != Decimal(offer.total_amount)
                    or approval.currency != offer.currency or offer.expires_at <= datetime.now(timezone.utc)):
                raise ValueError("Approved snapshot is stale or mismatched")
            assessment = session.scalar(select(OfferAssessment).where(OfferAssessment.offer_id == offer.id))
            if not assessment or assessment.verdict != "PASS":
                raise ValueError("Offer is not verified PASS")
            order = Order(case_id=case.id, offer_id=offer.id, approval_id=approval.id,
                          idempotency_key=data.idempotency_key, status="SIMULATED_CONFIRMED",
                          total_amount=offer.total_amount, currency=offer.currency)
            session.add(order)
            session.flush()
            order_id = order.id
            set_status(session, case, "MOCK_BOOKING", "booking_worker", "Booking Worker", "MOCK_ORDER_COMMITTED",
                       {"order_id": order_id})
    with SessionLocal() as session:
        saved = session.get(Order, order_id)
        if not saved or saved.status != "SIMULATED_CONFIRMED":
            raise RuntimeError("Committed order read-back failed")
        session.expunge(saved)
        return saved


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
        assessment = session.scalar(select(OfferAssessment).where(OfferAssessment.offer_id == approval.offer_id))
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
    if stale:
        raise ValueError("STALE_OFFER")
    return target, True
