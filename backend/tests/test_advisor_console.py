"""The advisor console: read-only access to any trip, traveler needs with an audit trail, and notes."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import advisor_login, create, get, login, postgres_available, wait_for

pytestmark = [pytest.mark.skipif(not postgres_available(), reason="Migrated PostgreSQL is unavailable"),
              pytest.mark.usefixtures("integration_mode")]


def test_an_advisor_reads_any_trip_but_cannot_act_on_it(override_settings):
    with TestClient(app) as client:
        owner = login(client)
        client.put("/api/auth/me/consent", json={"granted": True})
        client.put("/api/profile", json={"needs": {"wheelchair": "POWER", "medical_notes": "Oxygen at night."},
                                         "emergency_contact": {"name": "Sam", "phone": "021 1"}})
        case_id = create(client)
        wait_for(client, case_id, {"AWAITING_APPROVAL"})
        advisor_login(client, override_settings)
        case = get(client, f"/api/cases/{case_id}")
        assert case["my_role"] == "ADVISOR" and case["requirements"]["hard_constraints"]["needs"]["wheelchair"] == "POWER"
        for suffix in ("/offers", "/evidence", "/orders", "/events", "/approvals", "/trip-card"):
            assert client.get(f"/api/cases/{case_id}{suffix}").status_code == 200, suffix
        # Read-only: no nonce to approve with, and no writes.
        assert get(client, f"/api/cases/{case_id}/approvals")["nonce"] is None
        assert client.post(f"/api/cases/{case_id}/resume").status_code == 404
        assert client.post(f"/api/cases/{case_id}/help", json={"message": "x"}).status_code == 404
        listed = next(row for row in get(client, "/api/advisor/cases") if row["case_id"] == case_id)
        assert listed["traveler"] == owner and listed["status"] == "AWAITING_APPROVAL"
        profile = get(client, f"/api/advisor/cases/{case_id}/traveler")
        assert profile["needs"]["medical_notes"] == "Oxygen at night." and profile["emergency_contact"]["name"] == "Sam"
        assert client.post(f"/api/advisor/cases/{case_id}/notes", json={"text": "Confirmed oxygen delivery."}).status_code == 201
        assert [n["text"] for n in get(client, f"/api/advisor/cases/{case_id}/notes")] == ["Confirmed oxygen delivery."]
        login(client, owner)
        events = [e["event_type"] for e in get(client, f"/api/cases/{case_id}/events")]
        assert "ADVISOR_VIEWED_PROFILE" in events
        # Travelers cannot use the console.
        assert client.get(f"/api/advisor/cases/{case_id}/notes").status_code == 403
        assert client.get("/api/advisor/cases").status_code == 403
