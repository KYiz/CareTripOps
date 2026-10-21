"""Travelers and co-planners edit the illustrative outline; each save is a new version."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import create, get, login, new_email, postgres_available, wait_for

pytestmark = [pytest.mark.skipif(not postgres_available(), reason="Migrated PostgreSQL is unavailable"),
              pytest.mark.usefixtures("integration_mode")]
EDITABLE = ("day_number", "title", "note", "activities", "rest_note")


def test_travelers_edit_the_outline_as_a_new_version():
    with TestClient(app) as client:
        login(client)
        case_id = create(client)
        wait_for(client, case_id, {"AWAITING_APPROVAL"})
        case = get(client, f"/api/cases/{case_id}")
        base = case["itinerary_version"]
        days = [{key: day[key] for key in EDITABLE} for day in case["draft_itinerary"]]
        days[0] = {**days[0], "title": "Slow morning by the harbour", "activities": ["Coffee", "  ", "Short walk"]}
        path = f"/api/cases/{case_id}/itinerary"
        saved = client.put(path, json={"base_version": base, "days": days})
        assert saved.status_code == 200 and saved.json()["data"]["version"] == base + 1
        case = get(client, f"/api/cases/{case_id}")
        first = case["draft_itinerary"][0]
        assert case["itinerary_source"] == "TRAVELER_EDITED"
        assert first["title"] == "Slow morning by the harbour" and first["activities"] == ["Coffee", "Short walk"]
        # A save against an older version is refused instead of overwriting someone else's change.
        assert client.put(path, json={"base_version": base, "days": days}).json()["error"]["code"] == "ITINERARY_CHANGED"
        assert client.put(path, json={"base_version": base + 1, "days": days[1:]}).status_code == 400
        assert "ITINERARY_EDITED" in [e["event_type"] for e in get(client, f"/api/cases/{case_id}/events")]
        viewer = new_email()
        client.post(f"/api/cases/{case_id}/invitations", json={"email": viewer, "role": "VIEWER"})
        login(client, viewer)
        client.post(f"/api/invitations/{get(client, '/api/invitations')[0]['id']}", json={"accept": True})
        assert client.put(path, json={"base_version": base + 1, "days": days}).status_code == 403
