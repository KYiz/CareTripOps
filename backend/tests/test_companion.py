"""Departure reminders, the printable trip card and the help button."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.companion import queue_trip_reminders
from app.db import Notification, SessionLocal
from app.main import app
from tests.helpers import advisor_login, approve, create, get, login, new_email, postgres_available, wait_for

pytestmark = [pytest.mark.skipif(not postgres_available(), reason="Migrated PostgreSQL is unavailable"),
              pytest.mark.usefixtures("integration_mode")]


def booked_trip(client, family_role="CO_PLANNER"):
    """A booked Auckland trip whose traveler saved an emergency contact, with one family member."""
    owner = login(client)
    client.put("/api/auth/me/consent", json={"granted": True})
    client.put("/api/profile", json={"needs": {"wheelchair": "SOMETIMES"},
                                     "emergency_contact": {"name": "Ana", "relationship": "Daughter", "phone": "021 555 0100"}})
    case_id = create(client)
    wait_for(client, case_id, {"AWAITING_APPROVAL"})
    approve(client, case_id)
    wait_for(client, case_id, {"BOOKED"})
    family = new_email()
    client.post(f"/api/cases/{case_id}/invitations", json={"email": family, "role": family_role})
    login(client, family)
    client.post(f"/api/invitations/{get(client, '/api/invitations')[0]['id']}", json={"accept": True})
    login(client, owner)
    return owner, family, case_id


def reminders(case_id, template):
    with SessionLocal() as session:
        return session.scalar(select(func.count()).select_from(Notification)
                              .where(Notification.case_id == case_id, Notification.template == template))


def test_reminders_go_to_everyone_once_a_week_and_a_day_before():
    with TestClient(app) as client:
        _, _, case_id = booked_trip(client)
        departure = date.fromisoformat(get(client, f"/api/cases/{case_id}/orders")[0]["departure_date"])
        for _ in range(3):  # The worker looks every few minutes; each person still hears once.
            queue_trip_reminders(today=departure - timedelta(days=7))
        assert reminders(case_id, "TRIP_REMINDER_WEEK") == 2
        assert reminders(case_id, "TRIP_REMINDER_DAY") == 0
        queue_trip_reminders(today=departure - timedelta(days=1))
        queue_trip_reminders(today=departure - timedelta(days=1))
        assert reminders(case_id, "TRIP_REMINDER_DAY") == 2
        queue_trip_reminders(today=departure - timedelta(days=3))
        assert reminders(case_id, "TRIP_REMINDER_WEEK") + reminders(case_id, "TRIP_REMINDER_DAY") == 4


def test_the_trip_card_prints_the_stay_and_keeps_the_contact_for_the_traveler():
    with TestClient(app) as client:
        _, family, case_id = booked_trip(client)
        card = get(client, f"/api/cases/{case_id}/trip-card")
        assert card["stay"]["name"] == "Waterfront Accessible Suites" and card["booking_ref"].startswith("B-")
        assert set(card["stay"]["verified_claims"]) == {"lift_serves_all_guest_floors", "step_free_entry"}
        assert card["emergency_contact"]["phone"] == "021 555 0100" and card["emergency_number"] == "111"
        assert card["itinerary"] and card["destination"] == "Auckland"
        login(client, family)
        assert get(client, f"/api/cases/{case_id}/trip-card")["emergency_contact"] is None


def test_anyone_on_the_trip_can_ask_for_help_and_an_advisor_picks_it_up(override_settings):
    with TestClient(app) as client:
        owner, family, case_id = booked_trip(client, family_role="VIEWER")
        login(client, family)
        asked = client.post(f"/api/cases/{case_id}/help", json={"message": "Mum feels unwell at the hotel."})
        assert asked.status_code == 201
        with SessionLocal() as session:
            told = session.scalars(select(Notification.to_email).where(Notification.case_id == case_id,
                                                                       Notification.template == "HELP_REQUESTED")).all()
        assert owner in told and family not in told
        assert client.get("/api/advisor/help").status_code == 403
        advisor_login(client, override_settings)
        open_requests = [h for h in get(client, "/api/advisor/help") if h["case_id"] == case_id]
        assert open_requests[0]["message"] == "Mum feels unwell at the hotel." and open_requests[0]["email"] == family
        path = f"/api/advisor/help/{open_requests[0]['id']}"
        assert client.post(path, json={"note": "Called the hotel and the family."}).status_code == 200
        assert client.post(path, json={}).status_code == 409
        assert all(h["case_id"] != case_id for h in get(client, "/api/advisor/help"))
        login(client, owner)
        events = [e["event_type"] for e in get(client, f"/api/cases/{case_id}/events")]
        assert "HELP_REQUESTED" in events and "HELP_ACKNOWLEDGED" in events


def test_help_requests_are_rate_limited_per_trip():
    with TestClient(app) as client:
        _, _, case_id = booked_trip(client)
        codes = [client.post(f"/api/cases/{case_id}/help", json={"message": "Help"}).status_code for _ in range(6)]
        assert codes == [201] * 5 + [429]
