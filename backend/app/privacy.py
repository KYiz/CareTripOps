"""The traveler's own data: export, consent to sensitive details, and account deletion."""

from sqlalchemy import delete, select, update

from app.auth import now
from app.booking import SETTLED_ORDERS
from app.db import (Approval, Case, CaseInvitation, CaseMember, CaseNote, ConversationTurn, HelpRequest,
                    ItineraryProposal, ItineraryVersion, LoginCode, Notification, Order, Payment, Requirement,
                    SessionLocal, TravelerProfile, User, UserSession, add_event)

REDACTED = "[deleted at the traveler's request]"


def _iso(value):
    return value.isoformat() if value else None


def _money(value):
    return None if value is None else f"{value:.2f}"


def _owned_case(session, case: Case) -> dict:
    req = session.scalar(select(Requirement).where(Requirement.case_id == case.id))
    orders = session.scalars(select(Order).where(Order.case_id == case.id).order_by(Order.created_at)).all()
    return {
        "id": case.id, "status": case.status, "language": case.language, "created_at": _iso(case.created_at),
        "request": case.original_request,
        "requirements": req and {"destination": req.destination, "departure_date": _iso(req.departure_date),
                                 "traveler_count": req.traveler_count, "duration_days": req.duration_days,
                                 "budget": _money(req.budget), "currency": req.currency,
                                 "attractions": req.attractions, "needs": req.hard_constraints},
        "conversation": [{"role": t.role, "source": t.source, "text": t.text, "at": _iso(t.created_at)}
                         for t in session.scalars(select(ConversationTurn).where(ConversationTurn.case_id == case.id)
                                                  .order_by(ConversationTurn.id))],
        "itineraries": [{"version": v.version, "source": v.source, "days": v.days, "at": _iso(v.created_at)}
                        for v in session.scalars(select(ItineraryVersion).where(ItineraryVersion.case_id == case.id)
                                                 .order_by(ItineraryVersion.version))],
        "itinerary_requests": [{"request": p.request, "status": p.status, "at": _iso(p.created_at)}
                               for p in session.scalars(select(ItineraryProposal)
                                                        .where(ItineraryProposal.case_id == case.id))],
        "approvals": [{"status": a.status, "amount": _money(a.approved_amount), "currency": a.currency,
                       "decided_at": _iso(a.decided_at)}
                      for a in session.scalars(select(Approval).where(Approval.case_id == case.id))],
        "orders": [_order(session, order) for order in orders],
    }


def _order(session, order: Order) -> dict:
    payment = session.scalar(select(Payment).where(Payment.order_id == order.id))
    return {"id": order.id, "status": order.status, "total": _money(order.total_amount), "currency": order.currency,
            "departure_date": _iso(order.departure_date), "booking_ref": order.supplier_booking_ref,
            "refund": _money(order.refund_amount), "created_at": _iso(order.created_at),
            "payment": payment and {"provider": payment.provider, "status": payment.status,
                                    "amount": _money(payment.amount), "refunded": _money(payment.refunded_amount)}}


def export(user: User) -> dict:
    """Everything CareTrip holds about this person, as plain JSON."""
    with SessionLocal() as session:
        row = session.get(User, user.id)
        profile = session.get(TravelerProfile, user.id)
        memberships = session.execute(select(CaseMember, Case).join(Case, Case.id == CaseMember.case_id)
                                      .where(CaseMember.user_id == user.id).order_by(Case.created_at)).all()
        return {
            "exported_at": _iso(now()),
            "profile": {"email": row.email, "display_name": row.display_name, "created_at": _iso(row.created_at),
                        "last_login_at": _iso(row.last_login_at), "terms_version": row.terms_version,
                        "terms_accepted_at": _iso(row.terms_accepted_at),
                        "sensitive_data_consent_at": _iso(row.sensitive_consent_at)},
            "traveler_profile": profile and {"needs": profile.needs, "emergency_contact": profile.emergency_contact,
                                             "updated_at": _iso(profile.updated_at)},
            "trips": [_owned_case(session, case) for member, case in memberships if member.role == "OWNER"],
            "shared_with_me": [{"case_id": case.id, "role": member.role, "since": _iso(member.created_at)}
                               for member, case in memberships if member.role != "OWNER"],
            "help_requests": [{"case_id": h.case_id, "message": h.message, "at": _iso(h.created_at)}
                              for h in session.scalars(select(HelpRequest).where(HelpRequest.user_id == user.id))],
            "emails": [{"template": n.template, "status": n.status, "at": _iso(n.created_at)}
                       for n in session.scalars(select(Notification).where(Notification.to_email == row.email)
                                                .order_by(Notification.id))],
        }


def set_sensitive_consent(user_id: str, granted: bool) -> None:
    """Withdrawing consent also erases the health and accessibility details it covered."""
    with SessionLocal.begin() as session:
        row = session.get(User, user_id)
        row.sensitive_consent_at = (row.sensitive_consent_at or now()) if granted else None
        if not granted:
            session.execute(delete(TravelerProfile).where(TravelerProfile.user_id == user_id))


def delete_account(user: User) -> None:
    """Anonymize the account and redact its trips; booking records stay for accounting, without personal text."""
    with SessionLocal.begin() as session:
        owned = session.scalars(select(CaseMember.case_id).where(CaseMember.user_id == user.id,
                                                                 CaseMember.role == "OWNER")).all()
        if owned and session.scalar(select(Order.id).where(Order.case_id.in_(owned),
                                                           Order.status.not_in(SETTLED_ORDERS)).limit(1)):
            raise ValueError("ACTIVE_BOOKINGS")
        for case in session.scalars(select(Case).where(Case.id.in_(owned))):
            case.original_request, case.spoken_answers = REDACTED, {}
            add_event(session, case.id, "Privacy", "ACCOUNT_DELETED", case.status, {})
        if owned:
            session.execute(update(ConversationTurn).where(ConversationTurn.case_id.in_(owned)).values(text=REDACTED))
            session.execute(update(ItineraryProposal).where(ItineraryProposal.case_id.in_(owned))
                            .values(request=REDACTED))
            # Advisors' notes are about this traveler too.
            session.execute(update(CaseNote).where(CaseNote.case_id.in_(owned)).values(text=REDACTED))
            # Family members lose access to a trip whose traveler has left.
            session.execute(delete(CaseMember).where(CaseMember.case_id.in_(owned)))
            session.execute(update(CaseInvitation).where(CaseInvitation.case_id.in_(owned),
                                                         CaseInvitation.revoked_at.is_(None)).values(revoked_at=now()))
        session.execute(update(HelpRequest).where((HelpRequest.user_id == user.id) | HelpRequest.case_id.in_(owned))
                        .values(message=REDACTED))
        session.execute(delete(CaseMember).where(CaseMember.user_id == user.id))
        session.execute(update(CaseInvitation).where(CaseInvitation.email == user.email,
                                                     CaseInvitation.revoked_at.is_(None)).values(revoked_at=now()))
        identifiers = [user.email, *([f"tel:{user.phone}"] if user.phone else [])]
        session.execute(delete(LoginCode).where(LoginCode.identifier.in_(identifiers)))
        session.execute(update(Notification).where(Notification.to_email == user.email, Notification.status == "PENDING")
                        .values(status="CANCELLED"))
        anonymous = f"deleted+{user.id}@invalid"
        session.execute(update(Notification).where(Notification.to_email == user.email).values(to_email=anonymous))
        session.execute(update(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
                        .values(revoked_at=now()))
        row = session.get(User, user.id)
        row.email, row.display_name, row.deleted_at = anonymous, None, now()
        row.phone = row.phone_verified_at = None
        row.sensitive_consent_at = None
        session.execute(delete(TravelerProfile).where(TravelerProfile.user_id == user.id))
