"""Sign-in, sessions, cross-site protection and family roles."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import create, get, login, new_email, postgres_available, wait_for

pytestmark = [pytest.mark.skipif(not postgres_available(), reason="Migrated PostgreSQL is unavailable"),
              pytest.mark.usefixtures("integration_mode")]


def test_login_code_is_single_use_and_wrong_guesses_are_limited():
    with TestClient(app) as client:
        email = new_email()
        code = client.post("/api/auth/request-code", json={"email": email.upper()}).json()["data"]["dev_code"]
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(5):
            assert client.post("/api/auth/verify", json={"email": email, "code": wrong, "accept_terms": True}).status_code == 400
        # Five wrong guesses retire the code, even when the right one follows.
        assert client.post("/api/auth/verify", json={"email": email, "code": code, "accept_terms": True}).status_code == 400
        code = client.post("/api/auth/request-code", json={"email": email}).json()["data"]["dev_code"]
        assert client.post("/api/auth/verify", json={"email": email, "code": code, "accept_terms": True}).status_code == 200
        assert client.post("/api/auth/verify", json={"email": email, "code": code, "accept_terms": True}).status_code == 400
        assert get(client, "/api/auth/me")["email"] == email


def test_a_new_code_retires_the_previous_one():
    with TestClient(app) as client:
        email = new_email()
        first = client.post("/api/auth/request-code", json={"email": email}).json()["data"]["dev_code"]
        second = client.post("/api/auth/request-code", json={"email": email}).json()["data"]["dev_code"]
        if first != second:
            assert client.post("/api/auth/verify", json={"email": email, "code": first, "accept_terms": True}).status_code == 400
        assert client.post("/api/auth/verify", json={"email": email, "code": second, "accept_terms": True}).status_code == 200


def test_session_cookie_is_http_only_and_logout_revokes_it():
    with TestClient(app) as client:
        email = new_email()
        code = client.post("/api/auth/request-code", json={"email": email}).json()["data"]["dev_code"]
        response = client.post("/api/auth/verify", json={"email": email, "code": code, "accept_terms": True})
        cookie = response.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=lax" in cookie
        token = client.cookies["caretrip_session"]
        assert client.post("/api/auth/logout").status_code == 200
        client.cookies.set("caretrip_session", token)
        assert client.get("/api/auth/me").status_code == 401


def test_cross_site_writes_are_rejected():
    with TestClient(app) as client:
        login(client)
        response = client.post("/api/cases", json={"request": "Three travelers need an Auckland trip."},
                               headers={"origin": "https://evil.example"})
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "CROSS_SITE_REQUEST"
        response = client.post("/api/cases", json={"request": "Three travelers need an Auckland trip."},
                               headers={"sec-fetch-site": "cross-site"})
        assert response.status_code == 403


def test_family_roles_limit_what_each_member_can_do():
    with TestClient(app) as client:
        owner = login(client)
        case_id = create(client)
        base = f"/api/cases/{case_id}"
        assert wait_for(client, case_id, {"AWAITING_APPROVAL"})["status"] == "AWAITING_APPROVAL"
        viewer, planner = new_email(), new_email()
        assert client.post(f"{base}/invitations", json={"email": viewer, "role": "VIEWER"}).status_code == 201
        assert client.post(f"{base}/invitations", json={"email": planner, "role": "CO_PLANNER"}).status_code == 201
        assert client.post(f"{base}/invitations", json={"email": planner, "role": "ADMIN"}).status_code == 400
        assert client.post(f"{base}/invitations", json={"email": owner, "role": "VIEWER"}).status_code == 400
        assert {item["email"] for item in get(client, f"{base}/members")["invitations"]} == {viewer, planner}
        owner_approval = get(client, f"{base}/approvals")
        assert owner_approval["nonce"]

        for email in (viewer, planner):
            login(client, email)
            assert client.get(base).status_code == 404  # Not a member until the invitation is accepted.
            invitation = next(item for item in get(client, "/api/invitations") if item["case_id"] == case_id)
            assert client.post(f"/api/invitations/{invitation['id']}", json={"accept": True}).status_code == 200
            assert get(client, base)["case_id"] == case_id
            assert get(client, f"{base}/approvals")["nonce"] is None  # Only the traveler can approve.
            assert get(client, f"{base}/members")["invitations"] == []
            decision = client.post(f"{base}/approvals/{owner_approval['approval_id']}/decision", json={
                "decision": "APPROVE", "nonce": owner_approval["nonce"],
                "expected_state_version": owner_approval["case_state_version"]})
            assert decision.status_code == 403
            assert client.post(f"{base}/invitations", json={"email": new_email(), "role": "VIEWER"}).status_code == 403

        login(client, viewer)
        assert client.post(f"{base}/guide/messages", json={"message": "What is next?"}).status_code == 403
        login(client, planner)
        assert client.post(f"{base}/guide/messages", json={"message": "What is next?"}).status_code == 200

        login(client, owner)
        roster = get(client, f"{base}/members")
        assert {item["email"]: item["role"] for item in roster["members"]} == {
            owner: "OWNER", viewer: "VIEWER", planner: "CO_PLANNER"}
        planner_id = next(item["user_id"] for item in roster["members"] if item["email"] == planner)
        owner_id = next(item["user_id"] for item in roster["members"] if item["email"] == owner)
        assert client.delete(f"{base}/members/{owner_id}").status_code == 409
        assert client.delete(f"{base}/members/{planner_id}").status_code == 200
        login(client, planner)
        assert client.get(base).status_code == 404


def test_declined_and_revoked_invitations_grant_nothing():
    with TestClient(app) as client:
        login(client)
        case_id = create(client)
        declined, revoked = new_email(), new_email()
        client.post(f"/api/cases/{case_id}/invitations", json={"email": declined, "role": "VIEWER"})
        invitation_id = client.post(f"/api/cases/{case_id}/invitations",
                                    json={"email": revoked, "role": "VIEWER"}).json()["data"]["id"]
        assert client.delete(f"/api/cases/{case_id}/invitations/{invitation_id}").status_code == 200
        login(client, declined)
        invitation = get(client, "/api/invitations")[0]
        assert client.post(f"/api/invitations/{invitation['id']}", json={"accept": False}).status_code == 200
        assert client.get(f"/api/cases/{case_id}").status_code == 404
        assert client.post(f"/api/invitations/{invitation['id']}", json={"accept": True}).status_code == 404
        login(client, revoked)
        assert get(client, "/api/invitations") == []
        assert client.post(f"/api/invitations/{invitation_id}", json={"accept": True}).status_code == 404


def test_sign_in_email_failure_is_a_retryable_error(monkeypatch):
    import app.api.privacy as codes

    def broken(*args, **kwargs):
        raise ConnectionError("smtp down")
    monkeypatch.setattr(codes, "send_email", broken)
    with TestClient(app) as client:
        response = client.post("/api/auth/request-code", json={"email": new_email()})
        assert response.status_code == 503
        assert response.json()["error"] == {"code": "EMAIL_UNAVAILABLE", "retryable": True,
                                            "message": "We could not send the email right now. Please try again in a minute."}



def test_a_family_member_plans_then_hands_the_trip_to_the_traveler():
    with TestClient(app) as client:
        daughter = login(client)
        case_id = create(client)
        wait_for(client, case_id, {"AWAITING_APPROVAL"})
        mum = new_email()
        assert client.post(f"/api/cases/{case_id}/invitations", json={"email": mum, "role": "OWNER"}).status_code == 201
        login(client, mum)
        invitation = get(client, "/api/invitations")[0]
        assert invitation["role"] == "OWNER"
        assert client.post(f"/api/invitations/{invitation['id']}", json={"accept": True}).status_code == 200
        # Mum now decides; her daughter keeps helping. Neither saved needs, so the checked offers still stand.
        assert get(client, f"/api/cases/{case_id}")["my_role"] == "OWNER"
        assert get(client, f"/api/cases/{case_id}/approvals")["nonce"]
        roles = {m["email"]: m["role"] for m in get(client, f"/api/cases/{case_id}/members")["members"]}
        assert roles == {mum: "OWNER", daughter: "CO_PLANNER"}
        login(client, daughter)
        assert get(client, f"/api/cases/{case_id}/approvals")["nonce"] is None


def test_a_handover_with_different_needs_stops_the_old_plan():
    with TestClient(app) as client:
        login(client)
        case_id = create(client)
        wait_for(client, case_id, {"AWAITING_APPROVAL"})
        mum = new_email()
        client.post(f"/api/cases/{case_id}/invitations", json={"email": mum, "role": "OWNER"})
        login(client, mum)
        client.put("/api/auth/me/consent", json={"granted": True})
        client.put("/api/profile", json={"needs": {"wheelchair": "POWER"}})
        client.post(f"/api/invitations/{get(client, '/api/invitations')[0]['id']}", json={"accept": True})
        case = get(client, f"/api/cases/{case_id}")
        # The offers were checked without a power wheelchair in mind, so nothing can be approved as it stands.
        assert case["status"] == "HUMAN_REVIEW" and case["requirements"]["hard_constraints"]["needs"]["wheelchair"] == "POWER"
        approval = get(client, f"/api/cases/{case_id}/approvals")
        assert approval is None or approval["status"] == "EXPIRED"
