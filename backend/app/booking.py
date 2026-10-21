"""Order lifecycle: hold with the supplier, authorize payment, book, capture; cancel and refund.

Rules that keep money and inventory consistent:
- No database lock is held across a supplier or payment call. Each step reads state, calls out with an
  idempotency key derived from our own IDs, then records the result in a short transaction.
- The card is only captured after the supplier confirms. Any failure before that releases the hold.
- A retryable outage (SupplierUnavailable) propagates so the job is retried; nothing is half-recorded.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app import jobs, notify
from app.clock import nz_today
from app.config import settings
from app.db import (Approval, Case, Offer, Order, Payment, Requirement, SessionLocal, add_event, offer_verdict,
                    set_status)
from app.payments import PAYMENT_WINDOW_MINUTES, get_payments
from app.skills.destinations import local_name
from app.skills.domain import refund_percent
from app.suppliers import HoldExpired, PriceChanged, SoldOut, SupplierRejected, get_supplier

TERMINAL_CASE = {"BOOKED", "REJECTED", "HUMAN_REVIEW", "CANCELLED"}
# Orders in these states no longer involve the traveler's money or a supplier.
SETTLED_ORDERS = ("CANCELLED", "FAILED", "EXPIRED")


def now() -> datetime:
    return datetime.now(timezone.utc)


def money(value) -> str:
    return f"NZD {Decimal(value):.2f}"


def _payload(case: Case, offer: Offer, **extra) -> dict:
    with SessionLocal() as session:
        destination = session.scalar(select(Requirement.destination).where(Requirement.case_id == case.id))
    return {"destination": local_name(destination or offer.name or "", case.language),
            "product": offer.name or offer.catalog_product_id, "case_short": case.id[:8], **extra}


def open_order(case_id: str, approval_id: str) -> tuple[str, str]:
    """Create the order, hold inventory and authorize payment.
    Returns (AUTHORIZED | REQUIRES_ACTION | FAILED, order_id)."""
    with SessionLocal.begin() as session:
        case = session.get(Case, case_id, with_for_update=True)
        approval = session.get(Approval, approval_id)
        offer = session.get(Offer, approval.offer_id)
        assessment = offer_verdict(session, offer.id)
        if (approval.status != "APPROVED" or approval.case_id != case_id or offer.case_id != case_id
                or approval.offer_version != offer.version or Decimal(approval.approved_amount) != Decimal(offer.total_amount)
                or not assessment or assessment.verdict != "PASS"):
            raise ValueError("Approved snapshot is stale or mismatched")
        order = session.scalar(select(Order).where(Order.idempotency_key == f"booking:{approval_id}"))
        if not order:
            requirement = session.scalar(select(Requirement).where(Requirement.case_id == case_id))
            order = Order(case_id=case_id, offer_id=offer.id, approval_id=approval_id,
                          idempotency_key=f"booking:{approval_id}", status="PENDING_PAYMENT",
                          total_amount=offer.total_amount, currency=offer.currency,
                          departure_date=(requirement.departure_date if requirement else None) or case.demo_date)
            session.add(order)
            session.flush()
            add_event(session, case_id, "Booking Worker", "ORDER_OPENED", case.status, {"order_id": order.id})
        if order.status == "FAILED":
            return "FAILED", order.id
        order_id, hold_ref, offer_ref = order.id, order.supplier_hold_ref, offer.supplier_offer_ref
        amount, currency, name = Decimal(order.total_amount), order.currency, offer.name or offer.catalog_product_id
        payment = session.scalar(select(Payment).where(Payment.order_id == order_id))
        payment_status = payment.status if payment else None

    if not hold_ref:
        try:
            hold = get_supplier().hold(offer_ref, amount, key=f"hold:{order_id}")
        except (PriceChanged, SoldOut, SupplierRejected) as exc:
            fail_order(order_id, exc.code)
            return "FAILED", order_id
        with SessionLocal.begin() as session:
            order = session.get(Order, order_id, with_for_update=True)
            order.supplier_hold_ref, order.supplier_hold_expires_at = hold.hold_ref, hold.expires_at
            add_event(session, case_id, "Booking Worker", "SUPPLIER_HOLD_PLACED", session.get(Case, case_id).status,
                      {"order_id": order_id, "expires_at": hold.expires_at.isoformat()})

    if payment_status is None:
        base = settings.frontend_origin.rstrip("/")
        provider = get_payments()
        started = provider.authorize(
            order_id=order_id, amount=amount, currency=currency, description=f"CareTrip: {name}",
            success_url=f"{base}/mobile?caseId={case_id}&payment=return",
            cancel_url=f"{base}/mobile?caseId={case_id}&payment=cancelled", key=f"pay:{order_id}")
        with SessionLocal.begin() as session:
            session.add(Payment(order_id=order_id, provider=provider.name, provider_ref=started.provider_ref,
                                payment_intent_ref=started.payment_intent_ref, status=started.status,
                                amount=amount, currency=currency, checkout_url=started.checkout_url))
            case = session.get(Case, case_id, with_for_update=True)
            offer = session.get(Offer, session.get(Order, order_id).offer_id)
            if started.status == "AUTHORIZED":
                set_status(session, case, "BOOKING", "prepare_payment", "Booking Worker", "PAYMENT_AUTHORIZED",
                           {"order_id": order_id, "provider": provider.name})
            else:
                set_status(session, case, "AWAITING_PAYMENT", "prepare_payment", "Booking Worker", "PAYMENT_REQUESTED",
                           {"order_id": order_id, "provider": provider.name})
                notify.queue_for_members(session, case, "PAYMENT_NEEDED", _payload(case, offer))
        payment_status = started.status
    return ("AUTHORIZED" if payment_status in {"AUTHORIZED", "CAPTURED"} else "REQUIRES_ACTION"), order_id


def complete_order(order_id: str) -> str:
    """Book with the supplier, then capture. Safe to repeat: both calls are keyed by the order."""
    with SessionLocal() as session:
        order = session.get(Order, order_id)
        payment = session.scalar(select(Payment).where(Payment.order_id == order_id))
        if order.status in {"CONFIRMED", "FAILED"}:
            return order.status
        hold_ref, booking_ref = order.supplier_hold_ref, order.supplier_booking_ref
        offer_ref = session.get(Offer, order.offer_id).supplier_offer_ref
        payment_ref, intent_ref, amount = payment.provider_ref, payment.payment_intent_ref, Decimal(order.total_amount)
        payment_status = payment.status
    if payment_status not in {"AUTHORIZED", "CAPTURED"}:
        fail_order(order_id, "PAYMENT_NOT_AUTHORIZED")
        return "FAILED"
    if not booking_ref:
        try:
            booking_ref = _book(order_id, hold_ref, offer_ref, amount)
        except (HoldExpired, PriceChanged, SoldOut, SupplierRejected) as exc:
            fail_order(order_id, exc.code)
            return "FAILED"
        with SessionLocal.begin() as session:
            order = session.get(Order, order_id, with_for_update=True)
            order.supplier_booking_ref = booking_ref
            add_event(session, order.case_id, "Booking Worker", "SUPPLIER_BOOKED", session.get(Case, order.case_id).status,
                      {"order_id": order_id, "booking_ref": booking_ref})
    if payment_status != "CAPTURED":
        # A capture failure raises: the job retries and the keyed booking call above is a no-op.
        get_payments().capture(payment_ref, intent_ref, amount, key=f"capture:{order_id}")
    with SessionLocal.begin() as session:
        order = session.get(Order, order_id, with_for_update=True)
        payment = session.scalar(select(Payment).where(Payment.order_id == order_id).with_for_update())
        case = session.get(Case, order.case_id, with_for_update=True)
        offer = session.get(Offer, order.offer_id)
        order.status, payment.status = "CONFIRMED", "CAPTURED"
        add_event(session, case.id, "Booking Worker", "ORDER_CONFIRMED", case.status,
                  {"order_id": order_id, "booking_ref": booking_ref, "amount": str(order.total_amount)})
        notify.queue_for_members(session, case, "ORDER_CONFIRMED",
                                 _payload(case, offer, booking_ref=booking_ref, amount=money(order.total_amount)))
    return "CONFIRMED"


def _book(order_id: str, hold_ref: str, offer_ref: str, amount: Decimal) -> str:
    """Book the held room. If the payment arrived after the supplier's hold lapsed, hold again once at the
    approved price; a changed price or no rooms left ends the order instead."""
    supplier = get_supplier()
    try:
        return supplier.book(hold_ref, key=f"book:{order_id}").booking_ref
    except HoldExpired:
        renewed = supplier.hold(offer_ref, amount, key=f"rehold:{order_id}")
        with SessionLocal.begin() as session:
            order = session.get(Order, order_id, with_for_update=True)
            order.supplier_hold_ref, order.supplier_hold_expires_at = renewed.hold_ref, renewed.expires_at
            add_event(session, order.case_id, "Booking Worker", "SUPPLIER_HOLD_RENEWED",
                      session.get(Case, order.case_id).status, {"order_id": order_id})
        return supplier.book(renewed.hold_ref, key=f"book:{order_id}:renewed").booking_ref


def fail_order(order_id: str, reason: str) -> None:
    """Release any card hold, mark the order failed and hand the Case to an advisor."""
    with SessionLocal() as session:
        payment = session.scalar(select(Payment).where(Payment.order_id == order_id))
        release = payment and payment.status in {"REQUIRES_ACTION", "AUTHORIZED"}
        refs = (payment.provider_ref, payment.payment_intent_ref) if payment else (None, None)
    if release:
        get_payments().release(refs[0], refs[1], key=f"release:{order_id}")
    with SessionLocal.begin() as session:
        order = session.get(Order, order_id, with_for_update=True)
        if order.status == "FAILED":
            return
        payment = session.scalar(select(Payment).where(Payment.order_id == order_id).with_for_update())
        if payment and release:
            payment.status = "RELEASED"
        order.status, order.failure_reason = "FAILED", reason
        case = session.get(Case, order.case_id, with_for_update=True)
        offer = session.get(Offer, order.offer_id)
        if case.status not in TERMINAL_CASE:
            set_status(session, case, "HUMAN_REVIEW", "booking", "Booking Worker", "ORDER_FAILED",
                       {"order_id": order_id, "reason": reason})
        notify.queue_for_members(session, case, "ORDER_FAILED", _payload(case, offer, reason=reason))


def sync_payment(case_id: str) -> str | None:
    """Read the provider's view of the Case's open payment; resume the workflow when it settles."""
    with SessionLocal() as session:
        payment = session.scalar(select(Payment).join(Order, Order.id == Payment.order_id)
                                 .where(Order.case_id == case_id).order_by(Payment.created_at.desc()).limit(1))
        if not payment:
            return None
        payment_id, ref, known = payment.id, payment.provider_ref, payment.status
    if known not in {"REQUIRES_ACTION", "AUTHORIZED"}:
        return known
    state = get_payments().refresh(ref)
    with SessionLocal.begin() as session:
        payment = session.get(Payment, payment_id, with_for_update=True)
        case = session.get(Case, case_id, with_for_update=True)
        if state.payment_intent_ref:
            payment.payment_intent_ref = state.payment_intent_ref
        if state.status != payment.status and state.status in {"AUTHORIZED", "EXPIRED", "RELEASED", "FAILED"}:
            payment.status = state.status
            add_event(session, case_id, "Booking Worker", f"PAYMENT_{state.status}", case.status, {"payment_id": payment_id})
        if case.status == "AWAITING_PAYMENT" and payment.status != "REQUIRES_ACTION":
            try:
                jobs.enqueue(session, case_id, "resume")
            except jobs.JobAlreadyActive:
                pass
        return payment.status


def expire_stale_payments() -> list[str]:
    """Release checkouts left unpaid past the payment window, so inventory and card holds are not left open.
    The supplier hold alone does not decide: booking renews a lapsed hold if the traveler paid in time."""
    cutoff = now() - timedelta(minutes=PAYMENT_WINDOW_MINUTES + 1)
    with SessionLocal() as session:
        stale = session.scalars(select(Order.case_id).join(Case, Case.id == Order.case_id)
                                .join(Payment, Payment.order_id == Order.id).where(
            Case.status == "AWAITING_PAYMENT", Order.status == "PENDING_PAYMENT",
            Payment.status == "REQUIRES_ACTION", Payment.created_at < cutoff)).all()
    expired = []
    for case_id in stale:
        status = sync_payment(case_id)
        if status == "REQUIRES_ACTION":
            with SessionLocal() as session:
                payment = session.scalar(select(Payment).join(Order, Order.id == Payment.order_id)
                                         .where(Order.case_id == case_id).order_by(Payment.created_at.desc()).limit(1))
                ref, intent, order_id = payment.provider_ref, payment.payment_intent_ref, payment.order_id
            get_payments().release(ref, intent, key=f"expire:{order_id}")
            with SessionLocal.begin() as session:
                payment = session.scalar(select(Payment).where(Payment.order_id == order_id).with_for_update())
                payment.status = "EXPIRED"
                add_event(session, case_id, "Booking Worker", "PAYMENT_EXPIRED", "AWAITING_PAYMENT", {"order_id": order_id})
                try:
                    jobs.enqueue(session, case_id, "resume")
                except jobs.JobAlreadyActive:
                    pass
            expired.append(case_id)
    return expired


def cancellation_quote(order: Order, offer: Offer, today: date | None = None) -> tuple[int, Decimal]:
    # Deadlines count New Zealand calendar days, not the server's UTC date.
    percent = refund_percent(offer.cancellation_policy, order.departure_date, today or nz_today())
    return percent, (Decimal(order.total_amount) * percent / 100).quantize(Decimal("0.01"))


def request_cancellation(case_id: str, order_id: str) -> dict:
    """Record the traveler's request and queue the supplier cancellation and refund."""
    with SessionLocal.begin() as session:
        order = session.get(Order, order_id, with_for_update=True)
        if not order or order.case_id != case_id:
            raise LookupError("Order not found")
        if order.status != "CONFIRMED":
            raise ValueError("Only a confirmed booking can be cancelled")
        offer = session.get(Offer, order.offer_id)
        percent, refund = cancellation_quote(order, offer)
        order.status, order.refund_amount = "CANCELLATION_REQUESTED", refund
        case = session.get(Case, case_id, with_for_update=True)
        add_event(session, case_id, "Traveler", "CANCELLATION_REQUESTED", case.status,
                  {"order_id": order_id, "refund_percent": percent, "refund_amount": str(refund)})
        jobs.enqueue(session, case_id, "cancel", payload={"order_id": order_id})
        return {"order_id": order_id, "refund_percent": percent, "refund_amount": f"{refund:.2f}"}


def process_cancellation(order_id: str) -> None:
    with SessionLocal() as session:
        order = session.get(Order, order_id)
        payment = session.scalar(select(Payment).where(Payment.order_id == order_id))
        if order.status != "CANCELLATION_REQUESTED":
            return
        booking_ref, refund = order.supplier_booking_ref, Decimal(order.refund_amount or 0)
        intent_ref = payment.payment_intent_ref if payment else None
    get_supplier().cancel(booking_ref, key=f"cancel:{order_id}")
    if refund > 0:
        get_payments().refund(intent_ref, refund, key=f"refund:{order_id}")
    with SessionLocal.begin() as session:
        order = session.get(Order, order_id, with_for_update=True)
        payment = session.scalar(select(Payment).where(Payment.order_id == order_id).with_for_update())
        case = session.get(Case, order.case_id, with_for_update=True)
        offer = session.get(Offer, order.offer_id)
        order.status, order.cancelled_at = "CANCELLED", now()
        if payment:
            payment.refunded_amount = refund
            payment.status = ("REFUNDED" if refund >= Decimal(payment.amount) else
                              "PARTIALLY_REFUNDED" if refund > 0 else payment.status)
        set_status(session, case, "CANCELLED", "cancellation", "Booking Worker", "ORDER_CANCELLED",
                   {"order_id": order_id, "refund_amount": str(refund)})
        notify.queue_for_members(session, case, "ORDER_CANCELLED", _payload(case, offer, refund=money(refund)))


def cancellation_failed(order_id: str, reason: str) -> None:
    """The supplier would not cancel: put the booking back so the traveler can see it and try again."""
    with SessionLocal.begin() as session:
        order = session.get(Order, order_id, with_for_update=True)
        if order.status != "CANCELLATION_REQUESTED":
            return
        order.status, order.refund_amount = "CONFIRMED", None
        case = session.get(Case, order.case_id)
        add_event(session, case.id, "Booking Worker", "CANCELLATION_FAILED", case.status,
                  {"order_id": order_id, "reason": reason})
        notify.queue_for_members(session, case, "CANCELLATION_FAILED",
                                 _payload(case, session.get(Offer, order.offer_id), reason=reason))
