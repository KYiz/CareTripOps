"""The Stripe provider against stripe-mock (Stripe's official API emulator): request shapes and parsing.

Runs when STRIPE_MOCK_URL is set (Compose sets it). No Stripe account or key is involved.
"""
import json
import os
import time
from decimal import Decimal

import pytest

from app.payments import StripePaymentProvider

MOCK = os.environ.get("STRIPE_MOCK_URL")
pytestmark = pytest.mark.skipif(not MOCK, reason="stripe-mock is not available")


@pytest.fixture
def stripe_provider():
    return StripePaymentProvider("sk_test_123", MOCK)


def test_checkout_authorization_creates_a_hosted_session(stripe_provider):
    session = stripe_provider.authorize(order_id="order-1", amount=Decimal("920.00"), currency="NZD",
                                        description="CareTrip: Waterfront Accessible Suites",
                                        success_url="https://trip.example/ok", cancel_url="https://trip.example/no",
                                        key="pay:order-1")
    assert session.status == "REQUIRES_ACTION"
    assert session.provider_ref.startswith("cs_") and session.checkout_url


def test_refresh_reads_session_and_intent_state(stripe_provider):
    state = stripe_provider.refresh("cs_test_123")
    assert state.status in {"REQUIRES_ACTION", "AUTHORIZED", "CAPTURED", "RELEASED", "EXPIRED"}


def test_capture_release_and_refund_are_accepted(stripe_provider):
    stripe_provider.capture("cs_test_123", "pi_123", Decimal("920.00"), key="capture:order-1")
    stripe_provider.release("cs_test_123", "pi_123", key="release:order-1")
    stripe_provider.refund("pi_123", Decimal("460.00"), key="refund:order-1")


def test_webhook_signature_is_verified(stripe_provider, override_settings):
    import hashlib
    import hmac
    import stripe

    override_settings(stripe_webhook_secret="whsec_test")
    payload = json.dumps({"id": "evt_1", "object": "event", "type": "checkout.session.completed",
                          "data": {"object": {"id": "cs_test_1", "object": "checkout.session"}}})
    timestamp = int(time.time())
    signature = hmac.new(b"whsec_test", f"{timestamp}.{payload}".encode(), hashlib.sha256).hexdigest()
    event = stripe_provider.parse_webhook(payload.encode(), f"t={timestamp},v1={signature}")
    assert event["id"] == "evt_1"
    with pytest.raises(stripe.error.SignatureVerificationError):
        stripe_provider.parse_webhook(payload.encode(), f"t={timestamp},v1={'0' * 64}")
