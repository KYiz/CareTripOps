"""During and just before the trip: departure reminders, the printable trip card, and asking for help."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app import notify
from app.auth import now
from app.config import settings
from app.db import (Case, CaseMember, HelpRequest, ItineraryVersion, Offer, Order, Requirement, SessionLocal,
                    TravelerProfile, User, add_event, latest_claims)
from app.skills.destinations import local_name

NZ = ZoneInfo("Pacific/Auckland")
REMINDERS = {7: "TRIP_REMINDER_WEEK", 1: "TRIP_REMINDER_DAY"}


def nz_today() -> date:
    return datetime.now(NZ).date()


def _place(session, case: Case) -> str:
    destination = session.scalar(select(Requirement.destination).where(Requirement.case_id == case.id))
    return local_name(destination, case.language) if destination else ""


def queue_trip_reminders(today: date | None = None) -> int:
    """Remind everyone on a booked trip a week and a day before departure. Safe to call any number of times."""
    today = today or nz_today()
    queued = 0
    with SessionLocal.begin() as session:
        for days, template in REMINDERS.items():
            rows = session.execute(select(Order, Case, Offer).join(Case, Case.id == Order.case_id)
                                   .join(Offer, Offer.id == Order.offer_id)
                                   .where(Order.status == "CONFIRMED",
                                          Order.departure_date == today + timedelta(days=days))).all()
            for order, case, offer in rows:
                payload = {"destination": _place(session, case), "date": order.departure_date.isoformat(),
                           "stay": offer.name or "", "booking_ref": order.supplier_booking_ref or ""}
                queued += notify.queue_for_members(session, case, template, payload, dedupe=f"reminder:{order.id}:{days}")
    return queued


def trip_card(case_id: str, role: str) -> dict:
    """Everything a traveler needs on paper. The emergency contact is printed only for the traveler."""
    with SessionLocal() as session:
        case = session.get(Case, case_id)
        req = session.scalar(select(Requirement).where(Requirement.case_id == case_id))
        order = session.scalar(select(Order).where(Order.case_id == case_id, Order.status == "CONFIRMED")
                               .order_by(Order.created_at.desc()).limit(1))
        offer = session.get(Offer, order.offer_id) if order else None
        itinerary = session.scalar(select(ItineraryVersion).where(ItineraryVersion.case_id == case_id)
                                   .order_by(ItineraryVersion.version.desc()).limit(1))
        owner = session.execute(select(User, TravelerProfile).join(CaseMember, CaseMember.user_id == User.id)
                                .outerjoin(TravelerProfile, TravelerProfile.user_id == User.id)
                                .where(CaseMember.case_id == case_id, CaseMember.role == "OWNER")).first()
        contact = None
        if role == "OWNER" and owner and owner.TravelerProfile and owner.User.sensitive_consent_at:
            contact = owner.TravelerProfile.emergency_contact or None
        return {
            "case_id": case.id, "language": case.language, "traveler": owner.User.display_name if owner else None,
            "destination": req.destination if req else None, "travelers": req.traveler_count if req else None,
            "days": req.duration_days if req else None,
            "departure_date": order.departure_date.isoformat() if order and order.departure_date else None,
            "stay": offer and {"name": offer.name, "includes": offer.includes, "attributes": offer.attributes,
                               "verified_claims": [claim for claim, row in latest_claims(session, offer.id).items()
                                                   if row.verdict == "PASS" and claim != "no_access_need"]},
            "booking_ref": order.supplier_booking_ref if order else None,
            "cancellation_policy": offer.cancellation_policy if offer else [],
            "itinerary": itinerary.days if itinerary else [],
            "emergency_contact": contact, "support_phone": settings.support_phone or None, "emergency_number": "111",
        }


def request_help(case_id: str, user: User, message: str) -> dict:
    """Tell everyone else on the trip and the advisors straight away; the request stays open for an advisor."""
    text = message.strip()[:500] or "No details given."
    with SessionLocal.begin() as session:
        case = session.get(Case, case_id)
        row = HelpRequest(case_id=case_id, user_id=user.id, message=text)
        session.add(row)
        session.flush()
        payload = {"who": user.display_name or user.email, "destination": _place(session, case), "message": text}
        notified = (notify.queue_for_members(session, case, "HELP_REQUESTED", payload, exclude_user_id=user.id)
                    + notify.queue_for_advisors(session, case, "HELP_REQUESTED", payload))
        add_event(session, case_id, "Traveler", "HELP_REQUESTED", case.status, {"help_id": row.id})
        return {"id": row.id, "created_at": row.created_at.isoformat(), "notified": notified}


def open_help_requests() -> list[dict]:
    with SessionLocal() as session:
        rows = session.execute(select(HelpRequest, User, Requirement.destination)
                               .join(User, User.id == HelpRequest.user_id)
                               .outerjoin(Requirement, Requirement.case_id == HelpRequest.case_id)
                               .where(HelpRequest.acknowledged_at.is_(None)).order_by(HelpRequest.created_at)).all()
        return [{"id": help.id, "case_id": help.case_id, "message": help.message, "destination": destination,
                 "from": who.display_name or who.email, "email": who.email, "created_at": help.created_at.isoformat()}
                for help, who, destination in rows]


def acknowledge_help(help_id: str, advisor: User, note: str) -> bool:
    with SessionLocal.begin() as session:
        row = session.get(HelpRequest, help_id, with_for_update=True)
        if not row:
            raise LookupError(help_id)
        if row.acknowledged_at:
            return False
        row.acknowledged_by, row.acknowledged_at, row.advisor_note = advisor.id, now(), note.strip()[:2000] or None
        case = session.get(Case, row.case_id)
        add_event(session, row.case_id, "Travel Advisor", "HELP_ACKNOWLEDGED", case.status, {"help_id": row.id})
        return True
