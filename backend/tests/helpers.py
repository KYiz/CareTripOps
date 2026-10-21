"""Shared steps for the PostgreSQL-backed API tests: sign in, create a trip, wait, approve."""

import time
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.clock import nz_today
from app.db import engine


def postgres_available():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1 FROM cases LIMIT 1"))
        return True
    except Exception:
        return False


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


def wait_idle(case_id, timeout=10):
    """Wait until no workflow run is queued or running for the Case."""
    from app.jobs import active_job

    deadline = time.monotonic() + timeout
    while active_job(case_id):
        if time.monotonic() > deadline:
            pytest.fail(f"Case {case_id} still has an active run")
        time.sleep(0.05)


def new_email():
    return f"traveler-{uuid4().hex[:12]}@example.test"


def login(client, email=None):
    """Sign in through the real email-code flow (development returns the code) and keep the cookie."""
    email = email or new_email()
    client.cookies.clear()
    sent = client.post("/api/auth/request-code", json={"email": email})
    assert sent.status_code == 202, sent.text
    verified = client.post("/api/auth/verify", json={"email": email, "code": sent.json()["data"]["dev_code"],
                                                     "accept_terms": True})
    assert verified.status_code == 200, verified.text
    return email


def create(client, request=None):
    if "caretrip_session" not in client.cookies:
        login(client)
    body = {"request": request or "Three travelers need a three-day Auckland trip with a lift. Budget NZD 1000.",
            "demo_date": str(nz_today() + timedelta(days=7))}
    response = client.post("/api/cases", json=body)
    assert response.status_code == 201, response.text
    return response.json()["data"]["case_id"]


def approve(client, case_id):
    approval = get(client, f"/api/cases/{case_id}/approvals")
    response = client.post(f"/api/cases/{case_id}/approvals/{approval['approval_id']}/decision", json={
        "decision": "APPROVE", "nonce": approval["nonce"], "expected_state_version": approval["case_state_version"]})
    assert response.status_code == 200, response.text
    return approval


def advisor_login(client, override_settings):
    email = new_email()
    override_settings(advisor_emails=(email,))
    login(client, email)
    return email


def inject(operation, mode, count=1):
    from supplier_sim.app import inject as add_fault, Fault
    add_fault(Fault(operation=operation, mode=mode, count=count))


class FakeCheckout:
    """Behaves like Stripe Checkout: approval needs the traveler to pay on a hosted page."""
    name = "stripe"

    def __init__(self):
        self.state, self.calls = "REQUIRES_ACTION", []

    def authorize(self, **kwargs):
        from app.payments import PaymentSession
        self.calls.append("authorize")
        return PaymentSession(provider_ref=f"cs_test_{kwargs['order_id']}", status="REQUIRES_ACTION",
                              checkout_url="https://checkout.stripe.test/pay")

    def refresh(self, provider_ref):
        from app.payments import PaymentState
        return PaymentState(self.state, "pi_test")

    def capture(self, *args, **kwargs):
        self.calls.append("capture")

    def release(self, *args, **kwargs):
        self.calls.append("release")

    def refund(self, payment_intent_ref, amount, key):
        self.calls.append(("refund", str(amount)))

