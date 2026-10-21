"""What a travel advisor sees across trips: status at a glance, the traveler's needs, and working notes."""

from sqlalchemy import func, select

from app.db import (Case, CaseMember, CaseNote, HelpRequest, Order, Payment, Requirement, ReviewTask, SessionLocal,
                    TravelerProfile, User, add_event)

ACTIVE_LIMIT = 100


def _count(session, model, case_id, *conditions) -> int:
    return session.scalar(select(func.count()).select_from(model).where(model.case_id == case_id, *conditions))


def list_cases(status: str | None = None) -> list[dict]:
    """The most recently updated trips, with what needs attention first."""
    with SessionLocal() as session:
        query = (select(Case, Requirement.destination, User.email, User.display_name)
                 .outerjoin(Requirement, Requirement.case_id == Case.id)
                 .join(CaseMember, (CaseMember.case_id == Case.id) & (CaseMember.role == "OWNER"))
                 .join(User, User.id == CaseMember.user_id)
                 .order_by(Case.updated_at.desc()).limit(ACTIVE_LIMIT))
        if status:
            query = query.where(Case.status == status)
        rows = []
        for case, destination, email, name in session.execute(query).all():
            order = session.scalar(select(Order).where(Order.case_id == case.id).order_by(Order.created_at.desc()).limit(1))
            payment = order and session.scalar(select(Payment).where(Payment.order_id == order.id))
            rows.append({
                "case_id": case.id, "status": case.status, "destination": destination, "language": case.language,
                "traveler": name or email, "updated_at": case.updated_at.isoformat(),
                "open_reviews": _count(session, ReviewTask, case.id, ReviewTask.status == "OPEN"),
                "open_help": _count(session, HelpRequest, case.id, HelpRequest.acknowledged_at.is_(None)),
                "order": order and {"status": order.status, "total": f"{order.total_amount:.2f}", "currency": order.currency,
                                    "departure_date": order.departure_date.isoformat() if order.departure_date else None,
                                    "payment": payment and {"provider": payment.provider, "status": payment.status}},
            })
        rows.sort(key=lambda row: (-(row["open_help"] > 0), -(row["open_reviews"] > 0)))
        return rows


def traveler_profile(case_id: str, advisor: User) -> dict:
    """The traveler's consented needs, medical notes and emergency contact. Every read is recorded on the trip."""
    with SessionLocal.begin() as session:
        case = session.get(Case, case_id)
        if not case:
            raise LookupError(case_id)
        row = session.execute(select(User, TravelerProfile).join(CaseMember, CaseMember.user_id == User.id)
                              .outerjoin(TravelerProfile, TravelerProfile.user_id == User.id)
                              .where(CaseMember.case_id == case_id, CaseMember.role == "OWNER")).first()
        consented = bool(row and row.User.sensitive_consent_at and row.TravelerProfile)
        add_event(session, case_id, "Travel Advisor", "ADVISOR_VIEWED_PROFILE", case.status, {"advisor_id": advisor.id})
        return {"traveler": row.User.display_name or row.User.email if row else None,
                "email": row.User.email if row else None, "consent": consented,
                "needs": row.TravelerProfile.needs if consented else None,
                "emergency_contact": row.TravelerProfile.emergency_contact if consented else None}


def notes(case_id: str) -> list[dict]:
    with SessionLocal() as session:
        rows = session.execute(select(CaseNote, User).join(User, User.id == CaseNote.author_id)
                               .where(CaseNote.case_id == case_id).order_by(CaseNote.id)).all()
        return [{"id": note.id, "text": note.text, "author": author.display_name or author.email,
                 "created_at": note.created_at.isoformat()} for note, author in rows]


def add_note(case_id: str, advisor: User, text: str) -> dict:
    with SessionLocal.begin() as session:
        if not session.get(Case, case_id):
            raise LookupError(case_id)
        note = CaseNote(case_id=case_id, author_id=advisor.id, text=text.strip()[:4000])
        session.add(note)
        session.flush()
        return {"id": note.id, "text": note.text, "author": advisor.display_name or advisor.email,
                "created_at": note.created_at.isoformat()}
