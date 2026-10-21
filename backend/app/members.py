"""Family sharing: Case members and email invitations.

Roles: OWNER is the traveler and the only role that can approve a booking or manage members.
CO_PLANNER can help plan (clarify details, use the guide, resume). VIEWER can only read.

A family member may plan a trip for someone else and then hand it over: inviting a person as OWNER makes them the
traveler when they accept, and the previous owner stays on as CO_PLANNER.
"""

from datetime import timedelta

from sqlalchemy import select

from app.auth import now
from app.db import (Approval, Case, CaseInvitation, CaseMember, Order, Requirement, SessionLocal, User, add_event,
                    set_status)
from app import jobs, notify
from app.booking import SETTLED_ORDERS
from app.errors import fail
from app.workflow.state import owner_needs

INVITABLE_ROLES = {"VIEWER", "CO_PLANNER", "OWNER"}
# Offers were already checked against the previous owner's needs from these states on.
PRE_OFFER_STATES = {"RECEIVED", "NEEDS_CLARIFICATION", "REQUIREMENTS_READY", "HUMAN_REVIEW"}
INVITATION_DAYS = 14


def _open_invitations(session, **filters):
    query = select(CaseInvitation).where(CaseInvitation.accepted_at.is_(None), CaseInvitation.revoked_at.is_(None),
                                         CaseInvitation.expires_at > now())
    for key, value in filters.items():
        query = query.where(getattr(CaseInvitation, key) == value)
    return session.scalars(query.order_by(CaseInvitation.created_at)).all()


def list_members(case_id: str, include_invitations: bool) -> dict:
    with SessionLocal() as session:
        rows = session.execute(select(CaseMember, User).join(User, User.id == CaseMember.user_id)
                               .where(CaseMember.case_id == case_id).order_by(CaseMember.created_at)).all()
        members = [{"user_id": user.id, "email": user.email, "display_name": user.display_name,
                    "role": member.role, "joined_at": member.created_at.isoformat()} for member, user in rows]
        invitations = [{"id": item.id, "email": item.email, "role": item.role,
                        "expires_at": item.expires_at.isoformat()}
                       for item in _open_invitations(session, case_id=case_id)] if include_invitations else []
    return {"members": members, "invitations": invitations}


def invite(case_id: str, inviter: User, email: str, role: str) -> dict:
    if role not in INVITABLE_ROLES:
        fail("INVALID_ROLE", "Family members can be invited as VIEWER, CO_PLANNER or OWNER (hand over).", 400)
    if email == inviter.email:
        fail("INVITE_SELF", "You are already the traveler on this trip.", 400)
    with SessionLocal.begin() as session:
        case = session.get(Case, case_id, with_for_update=True)
        already = session.scalar(select(CaseMember).join(User, User.id == CaseMember.user_id)
                                 .where(CaseMember.case_id == case_id, User.email == email))
        if already:
            fail("ALREADY_MEMBER", "This person already has access to the trip.")
        for previous in _open_invitations(session, case_id=case_id, email=email):
            previous.revoked_at = now()
        session.flush()
        invitation = CaseInvitation(case_id=case_id, email=email, role=role, invited_by=inviter.id,
                                    expires_at=now() + timedelta(days=INVITATION_DAYS))
        session.add(invitation)
        session.flush()
        add_event(session, case_id, "Traveler", "MEMBER_INVITED", case.status, {"role": role})
        role_names = {"zh": {"VIEWER": "可查看", "CO_PLANNER": "协助规划", "OWNER": "出行人（接管这次行程）"},
                      "en": {"VIEWER": "viewer", "CO_PLANNER": "co-planner", "OWNER": "the traveler (taking over the trip)"}}
        notify.queue(session, to=email, template="MEMBER_INVITED", language=case.language, case_id=case_id,
                     payload={"inviter": inviter.display_name or inviter.email,
                              "role": role_names.get(case.language, role_names["en"])[role]})
        invitation_id = invitation.id
    return {"id": invitation_id, "email": email, "role": role}


def revoke_invitation(case_id: str, invitation_id: str) -> None:
    with SessionLocal.begin() as session:
        invitation = session.get(CaseInvitation, invitation_id)
        if not invitation or invitation.case_id != case_id or invitation.accepted_at or invitation.revoked_at:
            fail("INVITATION_NOT_FOUND", "Invitation not found", 404)
        invitation.revoked_at = now()


def remove_member(case_id: str, user_id: str) -> None:
    with SessionLocal.begin() as session:
        member = session.get(CaseMember, (case_id, user_id), with_for_update=True)
        if not member:
            fail("MEMBER_NOT_FOUND", "Member not found", 404)
        if member.role == "OWNER":
            fail("OWNER_REQUIRED", "The traveler cannot be removed from their own trip.")
        session.delete(member)
        case = session.get(Case, case_id)
        add_event(session, case_id, "Traveler", "MEMBER_REMOVED", case.status, {"role": member.role})


def my_invitations(user: User) -> list[dict]:
    with SessionLocal() as session:
        rows = _open_invitations(session, email=user.email)
        result = []
        for item in rows:
            inviter = session.get(User, item.invited_by)
            requirement = session.scalar(select(Requirement).where(Requirement.case_id == item.case_id))
            result.append({"id": item.id, "case_id": item.case_id, "role": item.role,
                           "invited_by": inviter.display_name or inviter.email,
                           "destination": requirement.destination if requirement else None,
                           "expires_at": item.expires_at.isoformat()})
        return result


def answer_invitation(user: User, invitation_id: str, accept: bool) -> dict:
    with SessionLocal.begin() as session:
        invitation = session.get(CaseInvitation, invitation_id, with_for_update=True)
        if (not invitation or invitation.email != user.email or invitation.accepted_at or invitation.revoked_at
                or invitation.expires_at <= now()):
            fail("INVITATION_NOT_FOUND", "This invitation is no longer available.", 404)
        if not accept:
            invitation.revoked_at = now()
            return {"case_id": invitation.case_id, "accepted": False}
        invitation.accepted_at = now()
        case = session.get(Case, invitation.case_id, with_for_update=True)
        if invitation.role == "OWNER":
            _hand_over(session, case, user)
        else:
            if not session.get(CaseMember, (invitation.case_id, user.id)):
                session.add(CaseMember(case_id=invitation.case_id, user_id=user.id, role=invitation.role))
            add_event(session, case.id, "Traveler", "MEMBER_JOINED", case.status, {"role": invitation.role})
        return {"case_id": invitation.case_id, "accepted": True, "role": invitation.role}


def _hand_over(session, case: Case, user: User) -> None:
    """Make `user` the traveler. Money already in motion stays with whoever started it, so that blocks a handover."""
    if jobs.active_job(case.id):
        fail("GRAPH_NOT_PAUSED", "The trip is still being prepared. Please try again in a moment.", retryable=True)
    if session.scalar(select(Order.id).where(Order.case_id == case.id, Order.status.not_in(SETTLED_ORDERS)).limit(1)):
        fail("HANDOVER_UNAVAILABLE", "This trip already has a booking in progress, so it cannot change hands.")
    previous = session.scalar(select(CaseMember).where(CaseMember.case_id == case.id, CaseMember.role == "OWNER"))
    if previous:
        previous.role = "CO_PLANNER"
    member = session.get(CaseMember, (case.id, user.id))
    if member:
        member.role = "OWNER"
    else:
        session.add(CaseMember(case_id=case.id, user_id=user.id, role="OWNER"))
    session.flush()
    add_event(session, case.id, "Traveler", "TRIP_HANDED_OVER", case.status, {})
    req = session.scalar(select(Requirement).where(Requirement.case_id == case.id))
    needs = owner_needs(session, case.id)
    if not req or req.hard_constraints.get("needs", {}) == needs:
        return
    req.hard_constraints = {**req.hard_constraints, "needs": needs}
    if case.status not in PRE_OFFER_STATES:
        # Offers were checked against someone else's needs: nothing may be approved until a person re-plans.
        for approval in session.scalars(select(Approval).where(Approval.case_id == case.id, Approval.status == "PENDING")):
            approval.status = "EXPIRED"
        set_status(session, case, "HUMAN_REVIEW", "handover", "Manager", "NEEDS_CHANGED_AFTER_HANDOVER", {})


def my_cases(user: User) -> list[dict]:
    with SessionLocal() as session:
        rows = session.execute(select(Case, CaseMember.role, Requirement.destination)
                               .join(CaseMember, CaseMember.case_id == Case.id)
                               .outerjoin(Requirement, Requirement.case_id == Case.id)
                               .where(CaseMember.user_id == user.id)
                               .order_by(Case.created_at.desc()).limit(100)).all()
        return [{"case_id": case.id, "role": role, "status": case.status, "destination": destination,
                 "created_at": case.created_at.isoformat()} for case, role, destination in rows]
