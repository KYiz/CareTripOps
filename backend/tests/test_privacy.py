"""Terms consent, step-up confirmation, the consented needs profile, data export and account deletion."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import engine
from app.main import app
from tests.helpers import approve, create, get, login, new_email, postgres_available, wait_for

pytestmark = [pytest.mark.skipif(not postgres_available(), reason="Migrated PostgreSQL is unavailable"),
              pytest.mark.usefixtures("integration_mode")]

NEEDS = {"wheelchair": "MANUAL", "max_walk_meters": 200, "step_free": True, "accessible_bathroom": True,
         "dietary": ["GLUTEN_FREE"], "medical_notes": "Insulin needs a fridge."}
CONTACT = {"name": "Mei Chen", "relationship": "Daughter", "phone": "+64 21 555 0100"}


def expire_confirmation(email):
    """As if the person signed in more than STEP_UP_MINUTES ago."""
    with engine.begin() as connection:
        connection.execute(text("UPDATE user_sessions SET reauthenticated_at = now() - interval '1 hour' "
                                "WHERE user_id = (SELECT id FROM users WHERE email = :email)"), {"email": email})


def step_up(client):
    code = client.post("/api/auth/step-up/request").json()["data"]["dev_code"]
    wrong = "000000" if code != "000000" else "111111"
    assert client.post("/api/auth/step-up/verify", json={"code": wrong}).json()["error"]["code"] == "LOGIN_CODE_INVALID"
    assert client.post("/api/auth/step-up/verify", json={"code": code}).status_code == 200


def error_code(response):
    return response.status_code, response.json()["error"]["code"]


def test_terms_are_accepted_once_per_version(monkeypatch):
    import app.auth as auth

    with TestClient(app) as client:
        email = new_email()
        code = client.post("/api/auth/request-code", json={"email": email}).json()["data"]["dev_code"]
        assert error_code(client.post("/api/auth/verify", json={"email": email, "code": code})) == (409, "TERMS_REQUIRED")
        # Asking for consent did not use up the code.
        verified = client.post("/api/auth/verify", json={"email": email, "code": code, "accept_terms": True})
        assert verified.status_code == 200 and verified.json()["data"]["terms_version"] == auth.TERMS_VERSION
        code = client.post("/api/auth/request-code", json={"email": email}).json()["data"]["dev_code"]
        assert client.post("/api/auth/verify", json={"email": email, "code": code}).status_code == 200
        monkeypatch.setattr(auth, "TERMS_VERSION", "2099-01")
        code = client.post("/api/auth/request-code", json={"email": email}).json()["data"]["dev_code"]
        assert error_code(client.post("/api/auth/verify", json={"email": email, "code": code})) == (409, "TERMS_REQUIRED")


def test_paying_and_cancelling_need_a_recent_confirmation():
    with TestClient(app) as client:
        email = login(client)
        case_id = create(client)
        wait_for(client, case_id, {"AWAITING_APPROVAL"})
        expire_confirmation(email)
        approval = get(client, f"/api/cases/{case_id}/approvals")
        decide = lambda decision: client.post(f"/api/cases/{case_id}/approvals/{approval['approval_id']}/decision", json={
            "decision": decision, "nonce": approval["nonce"], "expected_state_version": approval["case_state_version"]})
        assert error_code(decide("APPROVE")) == (403, "STEP_UP_REQUIRED")
        step_up(client)
        approve(client, case_id)
        wait_for(client, case_id, {"BOOKED"})
        order = get(client, f"/api/cases/{case_id}/orders")[0]
        expire_confirmation(email)
        path = f"/api/cases/{case_id}/orders/{order['id']}/cancel"
        assert error_code(client.post(path, json={"confirm": True})) == (403, "STEP_UP_REQUIRED")
        step_up(client)
        assert client.post(path, json={"confirm": True}).status_code == 200


def test_the_needs_profile_requires_consent_and_withdrawing_erases_it():
    with TestClient(app) as client:
        login(client)
        body = {"needs": NEEDS, "emergency_contact": CONTACT}
        assert error_code(client.put("/api/profile", json=body)) == (409, "CONSENT_REQUIRED")
        assert client.put("/api/auth/me/consent", json={"granted": True}).status_code == 200
        assert client.put("/api/profile", json=body).status_code == 200
        profile = get(client, "/api/profile")
        assert profile["needs"] == NEEDS and profile["emergency_contact"] == CONTACT and profile["consent"] is True
        assert get(client, "/api/auth/me")["sensitive_consent"] is True
        assert client.put("/api/profile", json={"needs": {**NEEDS, "wheelchair": "ROCKET"}}).status_code == 422
        assert client.put("/api/auth/me/consent", json={"granted": False}).status_code == 200
        profile = get(client, "/api/profile")
        assert profile["consent"] is False and profile["needs"]["wheelchair"] == "NONE" and profile["updated_at"] is None


def test_export_holds_my_trips_and_only_names_trips_shared_with_me():
    with TestClient(app) as client:
        owner = login(client)
        client.put("/api/auth/me/consent", json={"granted": True})
        client.put("/api/profile", json={"needs": NEEDS})
        case_id = create(client)
        wait_for(client, case_id, {"AWAITING_APPROVAL"})
        family = new_email()
        client.post(f"/api/cases/{case_id}/invitations", json={"email": family, "role": "VIEWER"})
        response = client.get("/api/auth/me/export")
        assert response.headers["content-disposition"].startswith("attachment")
        mine = response.json()["data"]
        assert mine["profile"]["email"] == owner and mine["traveler_profile"]["needs"] == NEEDS
        assert mine["trips"][0]["id"] == case_id and "Auckland" in mine["trips"][0]["request"]
        assert mine["trips"][0]["requirements"]["destination"] == "Auckland"
        login(client, family)
        client.post(f"/api/invitations/{get(client, '/api/invitations')[0]['id']}", json={"accept": True})
        theirs = client.get("/api/auth/me/export").json()["data"]
        assert theirs["trips"] == [] and theirs["shared_with_me"][0] == {
            "case_id": case_id, "role": "VIEWER", "since": theirs["shared_with_me"][0]["since"]}


def test_deleting_the_account_waits_for_bookings_then_anonymizes_everything():
    with TestClient(app) as client:
        owner = login(client)
        case_id = create(client)
        wait_for(client, case_id, {"AWAITING_APPROVAL"})
        approve(client, case_id)
        wait_for(client, case_id, {"BOOKED"})
        family = new_email()
        client.post(f"/api/cases/{case_id}/invitations", json={"email": family, "role": "CO_PLANNER"})
        login(client, family)
        client.post(f"/api/invitations/{get(client, '/api/invitations')[0]['id']}", json={"accept": True})
        login(client, owner)
        assert error_code(client.delete("/api/auth/me")) == (409, "ACTIVE_BOOKINGS")
        order = get(client, f"/api/cases/{case_id}/orders")[0]
        client.post(f"/api/cases/{case_id}/orders/{order['id']}/cancel", json={"confirm": True})
        wait_for(client, case_id, {"CANCELLED"})
        expire_confirmation(owner)
        assert error_code(client.delete("/api/auth/me")) == (403, "STEP_UP_REQUIRED")
        step_up(client)
        assert client.delete("/api/auth/me").status_code == 200
        assert client.get("/api/auth/me").status_code == 401
        with engine.connect() as connection:
            request = connection.execute(text("SELECT original_request FROM cases WHERE id = :id"), {"id": case_id}).scalar()
            left = connection.execute(text("SELECT count(*) FROM users WHERE email = :email"), {"email": owner}).scalar()
            turns = connection.execute(text("SELECT count(*) FROM conversation_turns WHERE case_id = :id "
                                            "AND text NOT LIKE '[deleted%'"), {"id": case_id}).scalar()
        assert request.startswith("[deleted") and left == 0 and turns == 0
        # Family members lose the trip; the booking record itself is kept for accounting.
        login(client, family)
        assert client.get(f"/api/cases/{case_id}").status_code == 404
        # The address can start again as a brand-new account.
        login(client, owner)
        assert get(client, "/api/cases") == []
