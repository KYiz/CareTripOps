"""Supplier failures, payments, cancellation, notifications and advisor reviews."""

import time
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from tests.helpers import (FakeCheckout, advisor_login, approve, create, get, inject, login, new_email,
                           postgres_available, wait_for, wait_idle)

pytestmark = [pytest.mark.skipif(not postgres_available(), reason="Migrated PostgreSQL is unavailable"),
              pytest.mark.usefixtures("integration_mode")]


def test_inconclusive_evidence_waits_for_an_advisor_who_can_pass_it(override_settings):
    with TestClient(app) as client:
        owner = login(client)
        # NZD 900 excludes B; A is blocked; C's lift coverage is unknown and goes to an advisor.
        case_id = create(client, "Three travelers need a three-day Auckland trip with a lift. Budget NZD 900.")
        assert wait_for(client, case_id, {"AWAITING_REVIEW", "HUMAN_REVIEW"})["status"] == "AWAITING_REVIEW"
        assert get(client, f"/api/cases/{case_id}/orders") == []
        assert client.get("/api/advisor/reviews").status_code == 403  # The traveler is not an advisor.
        advisor_login(client, override_settings)
        assert get(client, "/api/auth/me")["is_advisor"] is True
        task = next(t for t in get(client, "/api/advisor/reviews") if t["case_id"] == case_id)
        assert task["offer"]["product_id"] == "PACKAGE_C" and task["evidence"][0]["reference"] == "CAT-C-1"
        resolved = client.post(f"/api/advisor/reviews/{task['id']}", json={"decision": "PASS", "note": "Called the hotel."})
        assert resolved.status_code == 200 and resolved.json()["data"]["case_resumed"] is True
        assert client.post(f"/api/advisor/reviews/{task['id']}", json={"decision": "PASS"}).status_code == 409
        login(client, owner)
        assert wait_for(client, case_id, {"AWAITING_APPROVAL", "HUMAN_REVIEW"})["status"] == "AWAITING_APPROVAL"
        offers = {o["product_id"]: o for o in get(client, f"/api/cases/{case_id}/offers")}
        assert offers["PACKAGE_C"]["label"] == "VERIFIED" and offers["PACKAGE_C"]["reason_code"] == "ADVISOR_CONFIRMED"


def test_an_advisor_block_leaves_no_candidate_and_hands_off(override_settings):
    with TestClient(app) as client:
        owner = login(client)
        case_id = create(client, "Three travelers need a three-day Auckland trip with a lift. Budget NZD 900.")
        wait_for(client, case_id, {"AWAITING_REVIEW"})
        advisor_login(client, override_settings)
        task = next(t for t in get(client, "/api/advisor/reviews") if t["case_id"] == case_id)
        client.post(f"/api/advisor/reviews/{task['id']}", json={"decision": "BLOCK", "note": "Stairs at entry."})
        login(client, owner)
        assert wait_for(client, case_id, {"HUMAN_REVIEW", "AWAITING_APPROVAL"})["status"] == "HUMAN_REVIEW"


def test_supplier_price_change_fails_the_order_and_releases_payment():
    with TestClient(app) as client:
        case_id = create(client)
        wait_for(client, case_id, {"AWAITING_APPROVAL"})
        inject("hold", "price_change")
        approve(client, case_id)
        assert wait_for(client, case_id, {"HUMAN_REVIEW", "BOOKED"})["status"] == "HUMAN_REVIEW"
        order = get(client, f"/api/cases/{case_id}/orders")[0]
        assert (order["status"], order["failure_reason"], order["payment"]) == ("FAILED", "PRICE_CHANGED", None)
        from app.db import Notification
        with SessionLocal() as session:
            assert session.query(Notification).filter_by(case_id=case_id, template="ORDER_FAILED").count() == 1


def test_supplier_outage_is_retried_automatically(monkeypatch):
    import app.jobs as jobs_module
    monkeypatch.setattr(jobs_module, "RETRY_BASE_SECONDS", 0.2)
    with TestClient(app) as client:
        login(client)
        inject("search", "unavailable", count=3)  # One run: the first call plus the client's two retries.
        case_id = create(client)
        assert wait_for(client, case_id, {"AWAITING_APPROVAL", "RECOVERY_REQUIRED"})["status"] == "AWAITING_APPROVAL"
        wait_idle(case_id)  # The status is written a moment before the run records itself as done.
        from app.db import Job
        with SessionLocal() as session:
            job = session.query(Job).filter_by(case_id=case_id, kind="start").one()
            assert job.attempts == 2 and job.status == "DONE"


def test_cancellation_refunds_by_the_offer_policy_and_only_the_traveler_may_cancel():
    with TestClient(app) as client:
        owner = login(client)
        case_id = create(client)  # Departs in 7 days: B refunds 100% up to 7 days before.
        wait_for(client, case_id, {"AWAITING_APPROVAL"})
        approve(client, case_id)
        wait_for(client, case_id, {"BOOKED"})
        order = get(client, f"/api/cases/{case_id}/orders")[0]
        assert order["cancellation_quote"] == {"refund_percent": 100, "refund_amount": "920.00"}
        viewer = new_email()
        client.post(f"/api/cases/{case_id}/invitations", json={"email": viewer, "role": "CO_PLANNER"})
        login(client, viewer)
        client.post(f"/api/invitations/{get(client, '/api/invitations')[0]['id']}", json={"accept": True})
        path = f"/api/cases/{case_id}/orders/{order['id']}/cancel"
        assert client.post(path, json={"confirm": True}).status_code == 403
        login(client, owner)
        assert client.post(path, json={"confirm": False}).status_code == 400
        quote = client.post(path, json={"confirm": True}).json()["data"]
        assert quote == {"order_id": order["id"], "refund_percent": 100, "refund_amount": "920.00"}
        assert wait_for(client, case_id, {"CANCELLED"})["status"] == "CANCELLED"
        cancelled = get(client, f"/api/cases/{case_id}/orders")[0]
        assert cancelled["status"] == "CANCELLED" and cancelled["refund_amount"] == "920.00"
        assert cancelled["payment"]["status"] == "REFUNDED"
        assert client.post(path, json={"confirm": True}).status_code == 409  # Already cancelled.


def test_hosted_checkout_waits_for_payment_then_books_and_captures():
    from app.payments import set_payments
    checkout = FakeCheckout()
    set_payments(checkout)
    with TestClient(app) as client:
        owner = login(client)
        case_id = create(client)
        wait_for(client, case_id, {"AWAITING_APPROVAL"})
        viewer = new_email()
        client.post(f"/api/cases/{case_id}/invitations", json={"email": viewer, "role": "VIEWER"})
        approve(client, case_id)
        case = wait_for(client, case_id, {"AWAITING_PAYMENT", "BOOKED"})
        assert case["status"] == "AWAITING_PAYMENT" and case["next_action"] == "PAY"
        order = get(client, f"/api/cases/{case_id}/orders")[0]
        assert order["payment"]["checkout_url"] == "https://checkout.stripe.test/pay"
        login(client, viewer)
        client.post(f"/api/invitations/{get(client, '/api/invitations')[0]['id']}", json={"accept": True})
        assert get(client, f"/api/cases/{case_id}/orders")[0]["payment"]["checkout_url"] is None
        assert client.post(f"/api/cases/{case_id}/payments/sync").status_code == 403
        login(client, owner)
        wait_idle(case_id)
        # Still unpaid: syncing changes nothing.
        assert client.post(f"/api/cases/{case_id}/payments/sync").json()["data"]["payment_status"] == "REQUIRES_ACTION"
        checkout.state = "AUTHORIZED"  # The traveler paid on the hosted page.
        assert client.post(f"/api/cases/{case_id}/payments/sync").json()["data"]["payment_status"] == "AUTHORIZED"
        assert wait_for(client, case_id, {"BOOKED", "HUMAN_REVIEW"})["status"] == "BOOKED"
        assert checkout.calls.count("authorize") == 1 and checkout.calls.count("capture") == 1
        assert "release" not in checkout.calls


def test_abandoned_checkout_expires_and_releases_the_hold():
    from app.payments import set_payments
    checkout = FakeCheckout()
    set_payments(checkout)
    with TestClient(app) as client:
        case_id = create(client)
        wait_for(client, case_id, {"AWAITING_APPROVAL"})
        approve(client, case_id)
        wait_for(client, case_id, {"AWAITING_PAYMENT"})
        wait_idle(case_id)
        checkout.state = "EXPIRED"
        client.post(f"/api/cases/{case_id}/payments/sync")
        assert wait_for(client, case_id, {"HUMAN_REVIEW", "BOOKED"})["status"] == "HUMAN_REVIEW"
        order = get(client, f"/api/cases/{case_id}/orders")[0]
        assert (order["status"], order["failure_reason"]) == ("FAILED", "PAYMENT_NOT_COMPLETED")
        assert "capture" not in checkout.calls


def test_booking_notifications_reach_every_member_through_the_outbox():
    from app.db import Notification
    from app.notify import send_pending

    with TestClient(app) as client:
        login(client)
        case_id = create(client)
        wait_for(client, case_id, {"AWAITING_APPROVAL"})
        client.post(f"/api/cases/{case_id}/invitations", json={"email": new_email(), "role": "VIEWER"})
        approve(client, case_id)
        wait_for(client, case_id, {"BOOKED"})
        send_pending(limit=100)
        with SessionLocal() as session:
            rows = session.query(Notification).filter_by(case_id=case_id).all()
            assert {row.template for row in rows} >= {"MEMBER_INVITED", "ORDER_CONFIRMED"}
            assert all(row.status == "SENT" for row in rows)
            confirmed = next(row for row in rows if row.template == "ORDER_CONFIRMED")
            assert confirmed.payload["booking_ref"].startswith("B-")


def test_a_supplier_refusing_to_cancel_restores_the_booking():
    with TestClient(app) as client:
        case_id = create(client)
        wait_for(client, case_id, {"AWAITING_APPROVAL"})
        approve(client, case_id)
        wait_for(client, case_id, {"BOOKED"})
        order = get(client, f"/api/cases/{case_id}/orders")[0]
        inject("cancel", "reject")
        assert client.post(f"/api/cases/{case_id}/orders/{order['id']}/cancel", json={"confirm": True}).status_code == 200
        deadline = time.monotonic() + 10
        while get(client, f"/api/cases/{case_id}/orders")[0]["status"] != "CONFIRMED" and time.monotonic() < deadline:
            time.sleep(0.1)
        restored = get(client, f"/api/cases/{case_id}/orders")[0]
        assert restored["status"] == "CONFIRMED" and restored["cancellation_quote"]["refund_percent"] == 100
        assert any(e["event_type"] == "CANCELLATION_FAILED" for e in get(client, f"/api/cases/{case_id}/events"))
        # The traveler hears that the booking still stands, not that it failed.
        from app.db import Notification
        with SessionLocal() as session:
            templates = set(session.scalars(select(Notification.template).where(Notification.case_id == case_id)))
        assert "CANCELLATION_FAILED" in templates and "ORDER_FAILED" not in templates
        wait_idle(case_id)
        # The traveler can simply try again.
        assert client.post(f"/api/cases/{case_id}/orders/{order['id']}/cancel", json={"confirm": True}).status_code == 200
        assert wait_for(client, case_id, {"CANCELLED"})["status"] == "CANCELLED"


def test_advisor_queue_lists_only_trips_waiting_on_a_review(override_settings):
    with TestClient(app) as client:
        login(client)
        decided = create(client)  # B passes, so nothing is queued for this trip.
        waiting = create(client, "Three travelers need a three-day Auckland trip with a lift. Budget NZD 900.")
        wait_for(client, decided, {"AWAITING_APPROVAL"})
        wait_for(client, waiting, {"AWAITING_REVIEW"})
        advisor_login(client, override_settings)
        listed = {task["case_id"] for task in get(client, "/api/advisor/reviews")}
        assert waiting in listed and decided not in listed



def test_an_offer_that_expired_during_review_goes_to_a_person_once(override_settings, monkeypatch):
    from datetime import datetime, timedelta

    import app.skills.effects as effects

    class Later(datetime):  # The advisor took longer than the offer stays valid.
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(days=30)

    with TestClient(app) as client:
        owner = login(client)
        case_id = create(client, "Three travelers need a three-day Auckland trip with a lift. Budget NZD 900.")
        wait_for(client, case_id, {"AWAITING_REVIEW"})
        monkeypatch.setattr(effects, "datetime", Later)
        advisor_login(client, override_settings)
        task = next(t for t in get(client, "/api/advisor/reviews") if t["case_id"] == case_id)
        client.post(f"/api/advisor/reviews/{task['id']}", json={"decision": "PASS", "note": "Called the hotel."})
        login(client, owner)
        assert wait_for(client, case_id, {"HUMAN_REVIEW", "RECOVERY_REQUIRED"})["status"] == "HUMAN_REVIEW"
        wait_idle(case_id)
        events = [e["event_type"] for e in get(client, f"/api/cases/{case_id}/events")]
        assert "APPROVAL_NOT_PREPARED" in events and "RUN_FAILED" not in events


def test_a_payment_after_the_hold_lapsed_renews_the_hold_and_books():
    with TestClient(app) as client:
        case_id = create(client)
        wait_for(client, case_id, {"AWAITING_APPROVAL"})
        inject("book", "expired")  # The supplier's hold ran out before the payment arrived.
        approve(client, case_id)
        assert wait_for(client, case_id, {"BOOKED", "HUMAN_REVIEW", "RECOVERY_REQUIRED"})["status"] == "BOOKED"
        order = get(client, f"/api/cases/{case_id}/orders")[0]
        assert order["status"] == "CONFIRMED" and order["payment"]["status"] == "CAPTURED"
        assert "SUPPLIER_HOLD_RENEWED" in [e["event_type"] for e in get(client, f"/api/cases/{case_id}/events")]


def test_an_unpaid_checkout_lasts_the_payment_window_not_the_hold():
    from sqlalchemy import text as sql

    from app.booking import expire_stale_payments
    from app.payments import set_payments
    checkout = FakeCheckout()
    set_payments(checkout)
    with TestClient(app) as client:
        case_id = create(client)
        wait_for(client, case_id, {"AWAITING_APPROVAL"})
        approve(client, case_id)
        wait_for(client, case_id, {"AWAITING_PAYMENT"})
        wait_idle(case_id)

        def age(payment_minutes):
            with SessionLocal.begin() as session:
                session.execute(sql("UPDATE orders SET supplier_hold_expires_at = now() - interval '1 minute' "
                                    "WHERE case_id = :id"), {"id": case_id})
                session.execute(sql("UPDATE payments SET created_at = now() - make_interval(mins => :m) WHERE order_id IN "
                                    "(SELECT id FROM orders WHERE case_id = :id)"), {"id": case_id, "m": payment_minutes})

        age(25)  # The hold lapsed, but the traveler may still be paying.
        assert case_id not in expire_stale_payments()
        age(40)
        assert case_id in expire_stale_payments()
        assert wait_for(client, case_id, {"HUMAN_REVIEW", "BOOKED"})["status"] == "HUMAN_REVIEW"
        assert "release" in checkout.calls


def test_refund_deadlines_count_new_zealand_days(monkeypatch):
    from datetime import date, datetime, timezone
    from types import SimpleNamespace

    import app.clock as clock
    from app.booking import cancellation_quote

    class MorningInAuckland(datetime):  # 09:00 on 21 Oct in Auckland is still 20 Oct in UTC.
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 20, 20, 0, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(clock, "datetime", MorningInAuckland)
    order = SimpleNamespace(departure_date=date(2026, 10, 27), total_amount="900.00")
    offer = SimpleNamespace(cancellation_policy=[{"days_before": 7, "refund_percent": 100},
                                                 {"days_before": 2, "refund_percent": 50}])
    # Six New Zealand days before departure: half back, not the full refund a UTC date would give.
    assert cancellation_quote(order, offer) == (50, Decimal("450.00"))
