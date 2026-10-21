"""Checkout nodes: approval, payment, booking, and the ways a run ends."""

from langgraph.graph import END
from langgraph.types import interrupt
from sqlalchemy import select

from app.booking import complete_order, fail_order, open_order
from app.db import Approval, Case, Offer, Order, Payment, SessionLocal, add_event, set_status
from app.skills.contracts import ApprovalInput, ReviewInput
from app.skills.domain import generate_review
from app.skills.effects import prepare_approval
from app.workflow.state import FlowState


def approval_worker(state: FlowState) -> FlowState:
    with SessionLocal() as session:
        offer = session.get(Offer, state["final_offer_id"])
        data = ApprovalInput(case_id=state["case_id"], offer_id=offer.id, offer_version=offer.version,
                             amount=offer.total_amount, currency=offer.currency, expires_at=offer.expires_at)
    try:
        approval = prepare_approval(data)
    except ValueError as exc:
        # Typically the offer expired while an advisor reviewed it. Resuming would fail the same way, so a person
        # takes over instead of the run looping through recovery.
        with SessionLocal.begin() as session:
            case = session.get(Case, state["case_id"], with_for_update=True)
            set_status(session, case, "HUMAN_REVIEW", "prepare_approval", "Manager", "APPROVAL_NOT_PREPARED",
                       {"reason": str(exc)})
        return {"approval_id": ""}
    return {"approval_id": approval.id}


def route_prepared(state: FlowState) -> str:
    return "wait_approval" if state.get("approval_id") else END


def wait_approval(state: FlowState) -> FlowState:
    interrupt({"type": "approval", "approval_id": state["approval_id"]})
    return {}


def route_decision(state: FlowState) -> str:
    with SessionLocal() as session:
        approval = session.get(Approval, state["approval_id"])
        if approval.status == "APPROVED":
            return "prepare_payment"
        if approval.status == "REJECTED":
            return "rejected"
        return "human_review"


def prepare_payment_worker(state: FlowState) -> FlowState:
    status, order_id = open_order(state["case_id"], state["approval_id"])
    return {"order_id": order_id, "payment_status": status}


def route_payment(state: FlowState) -> str:
    return {"AUTHORIZED": "booking", "REQUIRES_ACTION": "wait_payment"}.get(state["payment_status"], END)


def wait_payment(state: FlowState) -> FlowState:
    interrupt({"type": "payment", "order_id": state["order_id"]})
    return {}


def route_after_payment(state: FlowState) -> str:
    with SessionLocal() as session:
        payment = session.scalar(select(Payment).where(Payment.order_id == state["order_id"]))
        return "booking" if payment and payment.status in {"AUTHORIZED", "CAPTURED"} else "payment_failed"


def payment_failed_worker(state: FlowState) -> FlowState:
    fail_order(state["order_id"], "PAYMENT_NOT_COMPLETED")
    return {}


def booking_worker(state: FlowState) -> FlowState:
    return {"order_status": complete_order(state["order_id"])}


def route_booking(state: FlowState) -> str:
    return "review" if state.get("order_status") == "CONFIRMED" else END


def review_worker(state: FlowState) -> FlowState:
    summary = generate_review(ReviewInput(case_id=state["case_id"], order_id=state["order_id"],
                                          offer_id=state["final_offer_id"]))
    with SessionLocal.begin() as session:
        case = session.get(Case, state["case_id"], with_for_update=True)
        order = session.get(Order, state["order_id"])
        if not order or order.case_id != case.id or order.status != "CONFIRMED":
            raise RuntimeError("Order read-back mismatch")
        if case.status != "BOOKED":
            set_status(session, case, "BOOKED", "review_worker", "Review Worker", "REVIEW_COMPLETED",
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

