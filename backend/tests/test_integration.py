"""PostgreSQL-backed API and checkpoint tests; run after `alembic upgrade head`."""
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from sqlalchemy.exc import DBAPIError
from sqlalchemy import text

from app.config import settings
from app.db import Approval, Case, Offer, SessionLocal, engine, set_status
from app.main import app
from app.skills.contracts import BookingInput
from app.skills.effects import decide_approval, execute_mock_booking


def postgres_available():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1 FROM cases LIMIT 1"))
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not postgres_available(), reason="Migrated PostgreSQL is unavailable")


@pytest.fixture(autouse=True)
def deterministic_integration_mode(monkeypatch):
    """Keep database acceptance tests independent of live Gemini quota and output."""
    import app.graph as graph_module
    import app.main as main_module
    import app.two_brains as planning_module

    mock_settings = replace(settings, model_mode="mock_llm")
    monkeypatch.setattr(graph_module, "settings", mock_settings)
    monkeypatch.setattr(main_module, "settings", mock_settings)
    monkeypatch.setattr(planning_module, "settings", mock_settings)
    monkeypatch.setenv("GEMINI_PLANNING_ENABLED", "false")


def get(client, path):
    response = client.get(path)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def wait_for(client, case_id, expected, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        case = get(client, f"/api/cases/{case_id}")
        if case["status"] in expected:
            return case
        time.sleep(0.1)
    pytest.fail(f"Case did not reach {expected}: {case}")


def create(client, request=None):
    body = {"request": request or "Three travelers need a three-day Auckland trip with a lift. Budget NZD 1000.",
            "demo_actor": "demo-user", "demo_date": str(date.today() + timedelta(days=7))}
    response = client.post("/api/cases", json=body)
    assert response.status_code == 201, response.text
    created = response.json()["data"]
    client.headers["X-Case-Token"] = created["access_token"]
    return created["case_id"]


def test_case_migration_columns_exist_once():
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT column_name, COUNT(*) FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = 'cases'
              AND column_name IN ('guide_state', 'access_token_hash')
            GROUP BY column_name
        """)).all()
    assert dict(rows) == {"guide_state": 1, "access_token_hash": 1}


def test_conflict_rerank_approval_and_idempotent_booking():
    with TestClient(app) as client:
        case_id = create(client)
        case = wait_for(client, case_id, {"AWAITING_APPROVAL", "RECOVERY_REQUIRED"})
        assert case["status"] == "AWAITING_APPROVAL"
        base = f"/api/cases/{case_id}"
        offers = get(client, f"{base}/offers")
        assert {o["product_id"]: o["label"] for o in offers} == {
            "PACKAGE_A": "BLOCKED", "PACKAGE_C": "REVIEW", "PACKAGE_B": "VERIFIED",
        }
        assert get(client, f"{base}/orders") == []
        events = get(client, f"{base}/events")
        assert any(e["event_type"] == "MANAGER_RERANK" for e in events)
        approval = get(client, f"{base}/approvals")
        payload = {"decision": "APPROVE", "nonce": approval["nonce"],
                   "expected_state_version": approval["case_state_version"]}
        decision_path = f"{base}/approvals/{approval['approval_id']}/decision"
        assert client.post(decision_path, json=payload).status_code == 200
        assert client.post(decision_path, json=payload).status_code == 200
        assert wait_for(client, case_id, {"DEMO_COMPLETED", "RECOVERY_REQUIRED"})["status"] == "DEMO_COMPLETED"
        orders = get(client, f"{base}/orders")
        assert len(orders) == 1 and orders[0]["total_amount"] == "920.00"
        assert orders[0]["offer_id"] == approval["offer_id"]
        replayed = execute_mock_booking(BookingInput(case_id=case_id, approval_id=approval["approval_id"],
                                                    offer_id=approval["offer_id"],
                                                    idempotency_key=f"mock-booking:{approval['approval_id']}"))
        assert replayed.id == orders[0]["id"]
        assert len(get(client, f"{base}/orders")) == 1


def test_case_id_alone_cannot_read_or_change_another_case():
    with TestClient(app) as client:
        first = create(client)
        first_token = client.headers["X-Case-Token"]
        second = create(client)
        second_token = client.headers["X-Case-Token"]
        assert wait_for(client, second, {"AWAITING_APPROVAL"})["status"] == "AWAITING_APPROVAL"
        client.headers.pop("X-Case-Token")
        for suffix in ("", "/offers", "/evidence", "/approvals", "/orders", "/events", "/guide"):
            assert client.get(f"/api/cases/{second}{suffix}").status_code == 403
        assert client.post(f"/api/cases/{second}/resume").status_code == 403
        client.headers["X-Case-Token"] = first_token
        assert client.get(f"/api/cases/{second}").status_code == 403
        client.headers["X-Case-Token"] = second_token
        assert get(client, f"/api/cases/{second}")["case_id"] == second


def test_live_guide_requires_case_token(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with TestClient(app) as client:
        case_id = create(client)
        token = client.headers["X-Case-Token"]
        path = f"/api/cases/{case_id}/guide/live"
        headers = {"origin": "http://localhost:8080"}
        with pytest.raises(WebSocketDisconnect) as missing:
            with client.websocket_connect(path, headers=headers):
                pass
        assert missing.value.code == 1008
        with pytest.raises(WebSocketDisconnect) as wrong:
            with client.websocket_connect(path, headers=headers, subprotocols=["case-token.wrong"]):
                pass
        assert wrong.value.code == 1008
        with pytest.raises(WebSocketDisconnect) as authorized:
            with client.websocket_connect(path, headers=headers, subprotocols=[f"case-token.{token}"]):
                pass
        assert authorized.value.code == 1013  # Authorization passed; live provider deliberately disabled.


def test_five_cases_keep_offers_and_approvals_isolated():
    with TestClient(app) as client:
        cases = []
        for _ in range(5):
            case_id = create(client)
            cases.append((case_id, client.headers["X-Case-Token"]))
        seen_approvals = set()
        seen_offers = set()
        for case_id, token in cases:
            client.headers["X-Case-Token"] = token
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
        assert wait_for(client, case_id, {"DEMO_COMPLETED", "RECOVERY_REQUIRED"})["status"] == "DEMO_COMPLETED"
        assert len(get(client, f"/api/cases/{case_id}/orders")) == 1


def test_recovery_after_committed_approval_creates_one_order():
    with TestClient(app) as client:
        case_id = create(client)
        assert wait_for(client, case_id, {"AWAITING_APPROVAL"})["status"] == "AWAITING_APPROVAL"
        approval = get(client, f"/api/cases/{case_id}/approvals")
        deadline = time.monotonic() + 5
        while case_id in app.state.tasks and time.monotonic() < deadline:
            time.sleep(0.05)
        assert case_id not in app.state.tasks
        status, changed = decide_approval(case_id, approval["approval_id"], "APPROVE",
                                          approval["nonce"], approval["case_state_version"])
        assert (status, changed) == ("APPROVED", True)
        with SessionLocal.begin() as session:
            case = session.get(Case, case_id, with_for_update=True)
            set_status(session, case, "RECOVERY_REQUIRED", "test_restart", "Manager",
                       "STARTUP_RECOVERY_REQUIRED", {})
        assert client.post(f"/api/cases/{case_id}/resume").status_code == 200
        assert wait_for(client, case_id, {"DEMO_COMPLETED", "RECOVERY_REQUIRED"})["status"] == "DEMO_COMPLETED"
        assert len(get(client, f"/api/cases/{case_id}/orders")) == 1


def test_safe_offer_without_accessibility_constraint():
    with TestClient(app) as client:
        case_id = create(client, "Three travelers need a three-day Auckland trip. Budget NZD 1000.")
        assert wait_for(client, case_id, {"AWAITING_APPROVAL"})["status"] == "AWAITING_APPROVAL"
        base = f"/api/cases/{case_id}"
        approval = get(client, f"{base}/approvals")
        selected = next(o for o in get(client, f"{base}/offers") if o["id"] == approval["offer_id"])
        assert selected["product_id"] == "PACKAGE_A" and selected["verdict"] == "PASS"
        assert not any(e["event_type"] == "MANAGER_RERANK" for e in get(client, f"{base}/events"))
        response = client.post(f"{base}/approvals/{approval['approval_id']}/decision", json={
            "decision": "APPROVE", "nonce": approval["nonce"],
            "expected_state_version": approval["case_state_version"],
        })
        assert response.status_code == 200
        assert wait_for(client, case_id, {"DEMO_COMPLETED"})["status"] == "DEMO_COMPLETED"
        assert [o["total_amount"] for o in get(client, f"{base}/orders")] == ["820.00"]


def test_rejection_and_cross_case_guard():
    with TestClient(app) as client:
        first = create(client)
        first_token = client.headers["X-Case-Token"]
        second = create(client)
        second_token = client.headers["X-Case-Token"]
        client.headers["X-Case-Token"] = first_token
        assert wait_for(client, first, {"AWAITING_APPROVAL"})["status"] == "AWAITING_APPROVAL"
        client.headers["X-Case-Token"] = second_token
        assert wait_for(client, second, {"AWAITING_APPROVAL"})["status"] == "AWAITING_APPROVAL"
        client.headers["X-Case-Token"] = first_token
        approval = get(client, f"/api/cases/{first}/approvals")
        payload = {"decision": "REJECT", "nonce": approval["nonce"],
                   "expected_state_version": approval["case_state_version"]}
        wrong = client.post(f"/api/cases/{second}/approvals/{approval['approval_id']}/decision", json=payload)
        assert wrong.status_code == 403
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
            deadline = time.monotonic() + 5
            while case_id in app.state.tasks and time.monotonic() < deadline:
                time.sleep(0.05)
            response = client.post(f"/api/cases/{case_id}/clarifications", json={"answers": answers})
            assert response.status_code == 200, response.text
            wait_for(client, case_id, {"NEEDS_CLARIFICATION", "HUMAN_REVIEW"})
        assert wait_for(client, case_id, {"HUMAN_REVIEW"})["status"] == "HUMAN_REVIEW"
        assert get(client, f"/api/cases/{case_id}/orders") == []


@pytest.mark.parametrize("failure", [TimeoutError("provider timed out"), ValueError("invalid JSON")])
def test_live_model_failure_never_falls_back(monkeypatch, failure):
    import app.graph as graph_module
    import app.main as main_module

    live_settings = replace(settings, model_mode="api")
    monkeypatch.setattr(graph_module, "settings", live_settings)
    monkeypatch.setattr(main_module, "settings", live_settings)
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-placeholder")

    def raise_failure(_):
        raise failure

    monkeypatch.setattr(graph_module, "extract_requirements_live", raise_failure)
    with TestClient(app) as client:
        case_id = create(client)
        assert wait_for(client, case_id, {"HUMAN_REVIEW"})["status"] == "HUMAN_REVIEW"
        assert get(client, f"/api/cases/{case_id}/orders") == []
        assert any(e["event_type"] == "MODEL_ERROR" for e in get(client, f"/api/cases/{case_id}/events"))
        with SessionLocal() as session:
            assert session.get(Case, case_id).llm_calls == 1


def test_no_pass_candidate_stops_in_human_review():
    with TestClient(app) as client:
        case_id = create(client, "Three travelers need a three-day Auckland trip with a lift. Budget NZD 900.")
        assert wait_for(client, case_id, {"HUMAN_REVIEW", "RECOVERY_REQUIRED"})["status"] == "HUMAN_REVIEW"
        assert get(client, f"/api/cases/{case_id}/orders") == []
        events = get(client, f"/api/cases/{case_id}/events")
        assert sum(event["event_type"] == "MANAGER_RERANK" for event in events) == 1
        assert any(event["event_type"] == "HUMAN_REVIEW_REQUIRED" for event in events)


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
