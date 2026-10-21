"""Orders, payments and cancellation."""

import logging

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app import booking, jobs
from app.api.common import envelope, iso, money
from app.auth import CaseAccess, case_role, require_recent_auth
from app.db import Offer, Order, Payment, PaymentEvent, SessionLocal
from app.errors import fail
from app.payments import get_payments

log = logging.getLogger("caretrip.api")
router = APIRouter()


class CancelOrder(BaseModel):
    confirm: bool


def _order_payload(session, order: Order, is_owner: bool) -> dict:
    payment = session.scalar(select(Payment).where(Payment.order_id == order.id))
    offer = session.get(Offer, order.offer_id)
    quote = booking.cancellation_quote(order, offer) if order.status == "CONFIRMED" else None
    return {
        "id": order.id, "case_id": order.case_id, "offer_id": order.offer_id, "approval_id": order.approval_id,
        "status": order.status, "total_amount": money(order.total_amount), "currency": order.currency,
        "departure_date": iso(order.departure_date), "supplier_booking_ref": order.supplier_booking_ref,
        "failure_reason": order.failure_reason, "refund_amount": money(order.refund_amount),
        "cancelled_at": iso(order.cancelled_at), "cancellation_policy": offer.cancellation_policy,
        "cancellation_quote": quote and {"refund_percent": quote[0], "refund_amount": f"{quote[1]:.2f}"},
        "payment": payment and {
            "provider": payment.provider, "status": payment.status, "refunded_amount": money(payment.refunded_amount),
            # The checkout link lets someone pay, so only the traveler receives it.
            "checkout_url": payment.checkout_url if is_owner and payment.status == "REQUIRES_ACTION" else None},
        "created_at": iso(order.created_at)}


@router.get("/api/cases/{case_id}/orders")
def orders(case_id: str, access: CaseAccess = Depends(case_role("VIEWER"))):
    with SessionLocal() as session:
        rows = session.scalars(select(Order).where(Order.case_id == case_id).order_by(Order.created_at)).all()
        return envelope([_order_payload(session, row, access.is_owner) for row in rows])


@router.post("/api/cases/{case_id}/orders/{order_id}/cancel")
def cancel_order(order_id: str, body: CancelOrder, access: CaseAccess = Depends(case_role("OWNER")),
                 _: None = Depends(require_recent_auth)):
    if not body.confirm:
        fail("CONFIRMATION_REQUIRED", "Please confirm the cancellation", 400)
    try:
        return envelope(booking.request_cancellation(access.case_id, order_id))
    except LookupError:
        fail("ORDER_NOT_FOUND", "Order not found", 404)
    except ValueError as exc:
        fail("INVALID_STATE", str(exc))
    except jobs.JobAlreadyActive:
        fail("GRAPH_NOT_PAUSED", "This trip is busy. Please try again in a moment.", retryable=True)


@router.post("/api/cases/{case_id}/payments/sync")
def sync_payment(access: CaseAccess = Depends(case_role("OWNER"))):
    """Called when the traveler returns from Stripe; the webhook does the same thing independently."""
    try:
        status = booking.sync_payment(access.case_id)
    except Exception:
        log.exception("payment sync failed", extra={"case_id": access.case_id})
        fail("PAYMENT_UNAVAILABLE", "Payment status could not be checked. Please try again.", 503, retryable=True)
    return envelope({"payment_status": status})


@router.post("/api/payments/stripe/webhook")
async def stripe_webhook(request: Request):
    provider = get_payments()
    if provider.name != "stripe":
        fail("NOT_CONFIGURED", "Stripe is not configured", 404)
    try:
        event = provider.parse_webhook(await request.body(), request.headers.get("stripe-signature", ""))
    except Exception:
        fail("INVALID_SIGNATURE", "Invalid webhook signature", 400)
    session_id = event["data"]["object"].get("id") if event["type"].startswith("checkout.session.") else None
    with SessionLocal.begin() as session:
        if session.get(PaymentEvent, event["id"]):
            return envelope({"duplicate": True})
        session.add(PaymentEvent(id=event["id"], event_type=event["type"]))
        case_id = session_id and session.scalar(select(Order.case_id).join(Payment, Payment.order_id == Order.id)
                                                .where(Payment.provider_ref == session_id))
    if case_id:
        await run_in_threadpool(booking.sync_payment, case_id)
    return envelope({"handled": bool(case_id)})

