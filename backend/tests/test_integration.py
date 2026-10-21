"""PostgreSQL-backed workflow tests: planning, offers, approval, recovery and the guide."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from sqlalchemy.exc import DBAPIError
from sqlalchemy import text

from app.config import settings
from app.db import Approval, Case, Offer, SessionLocal, engine
from app.main import app
from tests.helpers import approve, create, get, login, new_email, postgres_available, wait_for, wait_idle

pytestmark = [pytest.mark.skipif(not postgres_available(), reason="Migrated PostgreSQL is unavailable"),
              pytest.mark.usefixtures("integration_mode")]


def test_case_columns_after_account_migration():
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT column_name, COUNT(*) FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = 'cases'
              AND column_name IN ('guide_state', 'access_token_hash', 'live_session_count', 'selected_attraction')
            GROUP BY column_name
        """)).all()
    assert dict(rows) == {"live_session_count": 1, "selected_attraction": 1}


def test_ranking_evidence_approval_and_confirmed_booking():
    from app.booking import complete_order

    with TestClient(app) as client:
        case_id = create(client)
        assert wait_for(client, case_id, {"AWAITING_APPROVAL", "RECOVERY_REQUIRED"})["status"] == "AWAITING_APPROVAL"
        base = f"/api/cases/{case_id}"
        offers = {o["product_id"]: o for o in get(client, f"{base}/offers")}
        # Every offer is assessed: A's lift claim is contradicted, C's is unsettled, B's is supported.
        assert {p: o["label"] for p, o in offers.items()} == {
            "PACKAGE_A": "BLOCKED", "PACKAGE_C": "REVIEW", "PACKAGE_B": "VERIFIED"}
        # B passed, so C's inconclusive evidence is not worth an advisor's time: no review is opened.
        assert offers["PACKAGE_C"]["under_review"] is False
        assert offers["PACKAGE_B"]["ranking"]["score"] > offers["PACKAGE_A"]["ranking"]["score"]
        assert offers["PACKAGE_B"]["cancellation_policy"][0] == {"days_before": 7, "refund_percent": 100}
        assert all(source["url"] and source["content_hash"] for source in get(client, f"{base}/evidence")["sources"])
        assert get(client, f"{base}/orders") == []
        approval = approve(client, case_id)
        assert wait_for(client, case_id, {"BOOKED", "RECOVERY_REQUIRED", "HUMAN_REVIEW"})["status"] == "BOOKED"
        orders = get(client, f"{base}/orders")
        assert len(orders) == 1 and orders[0]["status"] == "CONFIRMED" and orders[0]["total_amount"] == "920.00"
        assert orders[0]["supplier_booking_ref"].startswith("B-")
        assert orders[0]["payment"] == {"provider": "simulated", "status": "CAPTURED", "refunded_amount": "0.00",
                                        "checkout_url": None}
        assert orders[0]["offer_id"] == approval["offer_id"]
        # Replaying the booking step is a no-op: same order, no second supplier booking.
        assert complete_order(orders[0]["id"]) == "CONFIRMED"
        assert len(get(client, f"{base}/orders")) == 1
        events = [e["event_type"] for e in get(client, f"{base}/events")]
        for expected in ("ORDER_OPENED", "SUPPLIER_HOLD_PLACED", "PAYMENT_AUTHORIZED", "SUPPLIER_BOOKED", "ORDER_CONFIRMED"):
            assert events.count(expected) == 1, expected


CASE_READS = ("", "/offers", "/evidence", "/approvals", "/orders", "/events", "/guide", "/members")


def test_signed_out_and_unrelated_users_cannot_reach_a_case():
    with TestClient(app) as client:
        owner = login(client)
        case_id = create(client)
        assert wait_for(client, case_id, {"AWAITING_APPROVAL"})["status"] == "AWAITING_APPROVAL"
        client.cookies.clear()
        for suffix in CASE_READS:
            assert client.get(f"/api/cases/{case_id}{suffix}").status_code == 401
        assert client.post("/api/cases", json={"request": "Auckland for three travelers"}).status_code == 401
        login(client)
        for suffix in CASE_READS:
            # Not a member: the Case is reported as missing, so IDs cannot be probed.
            assert client.get(f"/api/cases/{case_id}{suffix}").status_code == 404
        assert client.post(f"/api/cases/{case_id}/resume").status_code == 404
        assert all(item["case_id"] != case_id for item in get(client, "/api/cases"))
        login(client, owner)
        assert get(client, f"/api/cases/{case_id}")["case_id"] == case_id
        assert [item["case_id"] for item in get(client, "/api/cases")][:1] == [case_id]


def test_live_guide_requires_a_planning_member(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with TestClient(app) as client:
        owner = login(client)
        case_id = create(client)
        viewer = new_email()
        assert client.post(f"/api/cases/{case_id}/invitations", json={"email": viewer, "role": "VIEWER"}).status_code == 201
        path = f"/api/cases/{case_id}/guide/live"
        headers = {"origin": "http://localhost:8080"}

        def close_code():
            with pytest.raises(WebSocketDisconnect) as closed:
                with client.websocket_connect(path, headers=dict(headers)):
                    pass
            return closed.value.code

        client.cookies.clear()
        assert close_code() == 1008
        login(client)
        assert close_code() == 1008
        login(client, viewer)
        invitation = get(client, "/api/invitations")[0]
        assert client.post(f"/api/invitations/{invitation['id']}", json={"accept": True}).status_code == 200
        assert close_code() == 1008
        login(client, owner)
        assert close_code() == 1013  # Authorization passed; live provider deliberately disabled.


def test_five_cases_keep_offers_and_approvals_isolated():
    with TestClient(app) as client:
        cases = []
        for _ in range(5):
            cases.append(create(client))
        seen_approvals = set()
        seen_offers = set()
        for case_id in cases:
            assert wait_for(client, case_id, {"AWAITING_APPROVAL", "RECOVERY_REQUIRED"})["status"] == "AWAITING_APPROVAL"
            approval = get(client, f"/api/cases/{case_id}/approvals")
            offers = get(client, f"/api/cases/{case_id}/offers")
            assert approval["case_id"] == case_id
            assert all(offer["case_id"] == case_id for offer in offers)
            assert get(client, f"/api/cases/{case_id}/orders") == []
            seen_approvals.add(approval["approval_id"])
            seen_offers.update(offer["id"] for offer in offers)
        assert len(seen_approvals) == 5
        assert len(seen_offers) == 15


def test_concurrent_duplicate_approval_creates_one_order():
    with TestClient(app) as client:
        case_id = create(client)
        assert wait_for(client, case_id, {"AWAITING_APPROVAL", "RECOVERY_REQUIRED"})["status"] == "AWAITING_APPROVAL"
        approval = get(client, f"/api/cases/{case_id}/approvals")
        path = f"/api/cases/{case_id}/approvals/{approval['approval_id']}/decision"
        payload = {"decision": "APPROVE", "nonce": approval["nonce"],
                   "expected_state_version": approval["case_state_version"]}
        with ThreadPoolExecutor(max_workers=2) as workers:
            responses = list(workers.map(lambda _: client.post(path, json=payload), range(2)))
        assert [response.status_code for response in responses] == [200, 200]
        assert wait_for(client, case_id, {"BOOKED", "RECOVERY_REQUIRED"})["status"] == "BOOKED"
        assert len(get(client, f"/api/cases/{case_id}/orders")) == 1


def test_crash_after_supplier_booking_recovers_with_exactly_one_order(monkeypatch):
    """The worker dies after the supplier confirmed and payment was captured, before the step is checkpointed."""
    import app.graph as graph_module
    from supplier_sim.app import _state as supplier_state

    real_booking = graph_module.booking_worker
    crashes = []

    def booking_then_crash(state):
        result = real_booking(state)
        if not crashes:
            crashes.append(state["case_id"])
            raise RuntimeError("worker lost after commit")
        return result

    # build_graph runs in the app lifespan, so it picks up the patched node.
    monkeypatch.setattr(graph_module, "booking_worker", booking_then_crash)
    with TestClient(app) as client:
        case_id = create(client)
        assert wait_for(client, case_id, {"AWAITING_APPROVAL"})["status"] == "AWAITING_APPROVAL"
        approval = approve(client, case_id)
        assert wait_for(client, case_id, {"RECOVERY_REQUIRED", "BOOKED"})["status"] == "RECOVERY_REQUIRED"
        assert crashes == [case_id]
        assert [o["status"] for o in get(client, f"/api/cases/{case_id}/orders")] == ["CONFIRMED"]
        wait_idle(case_id)
        resumed = client.post(f"/api/cases/{case_id}/resume")
        assert resumed.status_code == 200 and resumed.json()["data"]["run_state"] == "queued"
        assert client.post(f"/api/cases/{case_id}/resume").status_code == 409  # Already resuming.
        # RECOVERY_REQUIRED is the starting state here, so wait only for terminal states.
        assert wait_for(client, case_id, {"BOOKED", "HUMAN_REVIEW"})["status"] == "BOOKED"
        orders = get(client, f"/api/cases/{case_id}/orders")
        assert len(orders) == 1 and orders[0]["approval_id"] == approval["approval_id"]
        assert len(supplier_state["bookings"]) == 1  # The supplier was booked once.


def test_safe_offer_without_accessibility_constraint():
    with TestClient(app) as client:
        case_id = create(client, "Three travelers need a three-day Auckland trip. Budget NZD 1000.")
        assert wait_for(client, case_id, {"AWAITING_APPROVAL"})["status"] == "AWAITING_APPROVAL"
        base = f"/api/cases/{case_id}"
        approval = get(client, f"{base}/approvals")
        selected = next(o for o in get(client, f"{base}/offers") if o["id"] == approval["offer_id"])
        # Without a lift requirement every offer passes; C wins on flexibility, rating and gentle walking.
        assert selected["product_id"] == "PACKAGE_C" and selected["verdict"] == "PASS"
        assert not any(e["event_type"] == "MANAGER_RERANK" for e in get(client, f"{base}/events"))
        response = client.post(f"{base}/approvals/{approval['approval_id']}/decision", json={
            "decision": "APPROVE", "nonce": approval["nonce"],
            "expected_state_version": approval["case_state_version"],
        })
        assert response.status_code == 200
        assert wait_for(client, case_id, {"BOOKED"})["status"] == "BOOKED"
        assert [o["total_amount"] for o in get(client, f"{base}/orders")] == ["880.00"]


def test_rejection_and_cross_case_guard():
    with TestClient(app) as client:
        first = create(client)
        second = create(client)
        assert wait_for(client, first, {"AWAITING_APPROVAL"})["status"] == "AWAITING_APPROVAL"
        assert wait_for(client, second, {"AWAITING_APPROVAL"})["status"] == "AWAITING_APPROVAL"
        approval = get(client, f"/api/cases/{first}/approvals")
        payload = {"decision": "REJECT", "nonce": approval["nonce"],
                   "expected_state_version": approval["case_state_version"]}
        # Same owner, wrong Case: the approval does not belong to this Case.
        wrong = client.post(f"/api/cases/{second}/approvals/{approval['approval_id']}/decision", json=payload)
        assert wrong.status_code == 409
        correct = client.post(f"/api/cases/{first}/approvals/{approval['approval_id']}/decision", json=payload)
        assert correct.status_code == 200
        assert wait_for(client, first, {"REJECTED"})["status"] == "REJECTED"
        assert get(client, f"/api/cases/{first}/orders") == []
        assert any(e["event_type"] == "APPROVAL_DECIDED" for e in get(client, f"/api/cases/{first}/events"))


def test_clarification_interrupt_and_resume():
    with TestClient(app) as client:
        case_id = create(client, "Auckland trip with a lift for three travelers")
        case = wait_for(client, case_id, {"NEEDS_CLARIFICATION"})
        assert "budget" in case["missing_fields"]
        response = client.post(f"/api/cases/{case_id}/clarifications", json={"answers": {
            "duration_days": 3, "budget": "1000", "currency": "NZD",
        }})
        assert response.status_code == 200, response.text
        assert wait_for(client, case_id, {"AWAITING_APPROVAL", "RECOVERY_REQUIRED"})["status"] == "AWAITING_APPROVAL"


def test_clarification_limit_stops_before_third_question():
    with TestClient(app) as client:
        case_id = create(client, "Auckland trip with a lift for three travelers")
        wait_for(client, case_id, {"NEEDS_CLARIFICATION"})
        for answers in ({"duration_days": 3}, {"budget": "1000"}):
            wait_idle(case_id)
            response = client.post(f"/api/cases/{case_id}/clarifications", json={"answers": answers})
            assert response.status_code == 200, response.text
            wait_for(client, case_id, {"NEEDS_CLARIFICATION", "HUMAN_REVIEW"})
        assert wait_for(client, case_id, {"HUMAN_REVIEW"})["status"] == "HUMAN_REVIEW"
        assert get(client, f"/api/cases/{case_id}/orders") == []


@pytest.mark.parametrize("failure", [TimeoutError("provider timed out"), ValueError("invalid JSON")])
def test_live_model_failure_never_falls_back(monkeypatch, override_settings, failure):
    import app.workflow.planning as planning

    override_settings(model_mode="api")  # On top of the fixture's embedded worker and test limits.
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-placeholder")

    def raise_failure(_):
        raise failure

    monkeypatch.setattr(planning, "extract_requirements_live", raise_failure)
    with TestClient(app) as client:
        case_id = create(client)
        assert wait_for(client, case_id, {"HUMAN_REVIEW"})["status"] == "HUMAN_REVIEW"
        assert get(client, f"/api/cases/{case_id}/orders") == []
        assert any(e["event_type"] == "MODEL_ERROR" for e in get(client, f"/api/cases/{case_id}/events"))
        with SessionLocal() as session:
            assert session.get(Case, case_id).llm_calls == 1


def test_stale_approval_amount_is_rejected():
    with TestClient(app) as client:
        case_id = create(client)
        wait_for(client, case_id, {"AWAITING_APPROVAL"})
        approval = get(client, f"/api/cases/{case_id}/approvals")
        with SessionLocal.begin() as session:
            row = session.get(Approval, approval["approval_id"], with_for_update=True)
            row.approved_amount = 999
        response = client.post(f"/api/cases/{case_id}/approvals/{approval['approval_id']}/decision", json={
            "decision": "APPROVE", "nonce": approval["nonce"],
            "expected_state_version": approval["case_state_version"],
        })
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "STALE_OFFER"
        assert get(client, f"/api/cases/{case_id}")["status"] == "HUMAN_REVIEW"
        assert any(e["event_type"] == "STALE_APPROVAL" for e in get(client, f"/api/cases/{case_id}/events"))
        assert get(client, f"/api/cases/{case_id}/orders") == []


def test_offer_snapshot_columns_are_database_immutable():
    with TestClient(app) as client:
        case_id = create(client)
        wait_for(client, case_id, {"AWAITING_APPROVAL"})
        offer = get(client, f"/api/cases/{case_id}/offers")[0]
        with pytest.raises(DBAPIError):
            with SessionLocal.begin() as session:
                row = session.get(Offer, offer["id"])
                row.total_amount = 1
        refreshed = next(item for item in get(client, f"/api/cases/{case_id}/offers") if item["id"] == offer["id"])
        assert refreshed["total_amount"] == offer["total_amount"]


def test_case_creation_is_rate_limited_per_client(override_settings):
    override_settings(case_create_limit_per_ip=2)
    with TestClient(app) as client:
        create(client)
        create(client)
        response = client.post("/api/cases", json={"request": "Three travelers need an Auckland trip."})
        assert response.status_code == 429
        assert response.json()["error"]["code"] == "RATE_LIMITED"
        assert response.json()["error"]["retryable"] is True
        assert int(response.headers["Retry-After"]) >= 1


def test_concurrent_live_session_reservations_respect_the_limit():
    from app.api.voice import release_live_session, reserve_live_session

    with TestClient(app) as client:
        case_id = create(client)
        with ThreadPoolExecutor(max_workers=6) as workers:
            claimed = list(workers.map(lambda _: reserve_live_session(case_id), range(6)))
        assert sorted(n for n in claimed if n is not None) == list(range(1, settings.max_live_sessions_per_case + 1))
        release_live_session(case_id)
        assert reserve_live_session(case_id) == settings.max_live_sessions_per_case
        with SessionLocal() as session:
            assert session.get(Case, case_id).live_session_count == settings.max_live_sessions_per_case


def test_failed_provider_connection_releases_the_voice_slot(monkeypatch):
    import sys
    import types as pytypes

    monkeypatch.setenv("GEMINI_API_KEY", "test-only-placeholder")

    class FailingClient:
        def __init__(self, **_):
            raise ConnectionError("provider unreachable")

    fake_genai = pytypes.SimpleNamespace(Client=FailingClient)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", pytypes.SimpleNamespace())
    monkeypatch.setattr(sys.modules["google"], "genai", fake_genai, raising=False)
    with TestClient(app) as client:
        case_id = create(client)
        with client.websocket_connect(f"/api/cases/{case_id}/guide/live",
                                      headers={"origin": "http://localhost:8080"}) as socket:
            assert socket.receive_json()["event"] == "error"
        with SessionLocal() as session:
            assert session.get(Case, case_id).live_session_count == 0


def test_api_docs_are_served_outside_production():
    with TestClient(app) as client:
        assert client.get("/api/docs").status_code == 200
        assert client.get("/api/openapi.json").status_code == 200


def test_guide_conversation_proposals_and_itinerary_versions_persist():
    from app.db import ConversationTurn, ItineraryProposal, ItineraryVersion

    with TestClient(app) as client:
        case_id = create(client)
        base = f"/api/cases/{case_id}"
        wait_for(client, case_id, {"AWAITING_APPROVAL"})
        guide = get(client, f"{base}/guide")
        assert guide["itinerary_version"] == 1 and guide["proposal"] is None
        second_place = guide["attractions"][1]
        assert client.post(f"{base}/guide/attraction", json={"attraction": second_place}).status_code == 200
        assert client.post(f"{base}/guide/attraction", json={"attraction": "Milford Sound"}).status_code == 422
        assert client.post(f"{base}/guide/messages", json={"message": "I am tired, make it slower"}).status_code == 200
        first = get(client, f"{base}/guide")
        assert first["selected_attraction"] == second_place
        assert [turn["role"] for turn in first["conversation"]] == ["traveler", "guide"]

        assert client.post(f"{base}/guide/revisions", json={"request": "Make it gentler"}).status_code == 200
        older = get(client, f"{base}/guide")["proposal"]
        assert client.post(f"{base}/guide/revisions", json={"request": "Even gentler please"}).status_code == 200
        proposal = get(client, f"{base}/guide")["proposal"]
        assert proposal["id"] != older["id"] and proposal["status"] == "PENDING"
        # Only the latest proposal can be decided; the older one was superseded.
        assert client.post(f"{base}/guide/revisions/decision",
                           json={"proposal_id": older["id"], "accept": True}).status_code == 409
        decided = client.post(f"{base}/guide/revisions/decision", json={"proposal_id": proposal["id"], "accept": True})
        assert decided.status_code == 200
        after = decided.json()["data"]
        assert after["itinerary_version"] == 2 and after["proposal"]["status"] == "ACCEPTED"
        assert after["days"] == proposal["days"]
        assert get(client, base)["itinerary_version"] == 2
        assert client.post(f"{base}/guide/revisions/decision",
                           json={"proposal_id": proposal["id"], "accept": True}).status_code == 409
        with SessionLocal() as session:
            assert session.query(ConversationTurn).filter_by(case_id=case_id).count() == 2
            assert [v.version for v in session.query(ItineraryVersion).filter_by(case_id=case_id)
                    .order_by(ItineraryVersion.version)] == [1, 2]
            statuses = sorted(p.status for p in session.query(ItineraryProposal).filter_by(case_id=case_id))
            assert statuses == ["ACCEPTED", "SUPERSEDED"]


def test_a_chinese_request_produces_a_chinese_trip_and_guide():
    with TestClient(app) as client:
        login(client)
        response = client.post("/api/cases", headers={"accept-language": "zh"}, json={
            "request": "我们三个人想去奥克兰轻松玩三天，总预算 1000 纽币，需要能到所有客房楼层的电梯。",
            "demo_date": str(date.today() + timedelta(days=7))})
        assert response.status_code == 201
        case_id = response.json()["data"]["case_id"]
        case = wait_for(client, case_id, {"AWAITING_APPROVAL", "RECOVERY_REQUIRED", "HUMAN_REVIEW"})
        assert case["status"] == "AWAITING_APPROVAL"  # Same A/C/B evidence path as the English sample.
        assert case["requirements"]["hard_constraints"]["elevator_required"] is True
        assert "游览" in case["draft_itinerary"][0]["title"]
        reply = client.post(f"/api/cases/{case_id}/guide/messages", headers={"accept-language": "zh-CN"},
                            json={"message": "下一站是哪里？"}).json()["data"]
        assert reply["intent"] == "NEXT_ACTIVITY" and "下一站" in reply["reply"]
        with SessionLocal() as session:
            assert session.get(Case, case_id).language == "zh"

