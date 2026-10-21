"""Payments: authorize at approval, capture only after the supplier confirms, release or refund otherwise.

Card details never touch CareTrip: Stripe Checkout collects them on Stripe's page. The simulated
provider authorizes instantly and is labelled "simulated" everywhere it appears.
"""

import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Protocol

from app.config import settings


@dataclass(frozen=True)
class PaymentSession:
    provider_ref: str
    status: str  # REQUIRES_ACTION | AUTHORIZED
    checkout_url: str | None = None
    payment_intent_ref: str | None = None


@dataclass(frozen=True)
class PaymentState:
    status: str  # REQUIRES_ACTION | AUTHORIZED | CAPTURED | RELEASED | EXPIRED | FAILED
    payment_intent_ref: str | None = None


def cents(amount: Decimal) -> int:
    return int((Decimal(amount) * 100).to_integral_value())


class PaymentProvider(Protocol):
    name: str

    def authorize(self, *, order_id: str, amount: Decimal, currency: str, description: str,
                  success_url: str, cancel_url: str, key: str) -> PaymentSession: ...
    def refresh(self, provider_ref: str) -> PaymentState: ...
    def capture(self, provider_ref: str, payment_intent_ref: str | None, amount: Decimal, key: str) -> None: ...
    def release(self, provider_ref: str, payment_intent_ref: str | None, key: str) -> None: ...
    def refund(self, payment_intent_ref: str | None, amount: Decimal, key: str) -> None: ...


class SimulatedPaymentProvider:
    """Development stand-in: every authorization succeeds and nothing is charged."""
    name = "simulated"

    def authorize(self, *, order_id, amount, currency, description, success_url, cancel_url, key):
        return PaymentSession(provider_ref=f"sim_{uuid.uuid5(uuid.NAMESPACE_URL, key).hex}", status="AUTHORIZED")

    def refresh(self, provider_ref):
        return PaymentState("AUTHORIZED")

    def capture(self, provider_ref, payment_intent_ref, amount, key):
        return None

    def release(self, provider_ref, payment_intent_ref, key):
        return None

    def refund(self, payment_intent_ref, amount, key):
        return None


class StripePaymentProvider:
    """Stripe Checkout with a manual-capture PaymentIntent (an authorization hold)."""
    name = "stripe"

    def __init__(self, secret_key: str, api_base: str = ""):
        import stripe
        self.stripe = stripe
        stripe.api_key = secret_key
        if api_base:
            stripe.api_base = api_base  # stripe-mock in tests
        stripe.max_network_retries = 2

    def authorize(self, *, order_id, amount, currency, description, success_url, cancel_url, key):
        session = self.stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"quantity": 1, "price_data": {"currency": currency.lower(), "unit_amount": cents(amount),
                                                       "product_data": {"name": description[:120]}}}],
            payment_intent_data={"capture_method": "manual", "metadata": {"order_id": order_id}},
            metadata={"order_id": order_id},
            success_url=success_url, cancel_url=cancel_url,
            # Stripe requires at least 30 minutes; the supplier hold is renewed or the order fails if it lapses.
            expires_at=int((datetime.now(timezone.utc) + timedelta(minutes=31)).timestamp()),
            idempotency_key=key,
        )
        return PaymentSession(provider_ref=session.id, status="REQUIRES_ACTION", checkout_url=session.url)

    def refresh(self, provider_ref):
        session = self.stripe.checkout.Session.retrieve(provider_ref, expand=["payment_intent"])
        intent = session.get("payment_intent")
        if isinstance(intent, str):  # Not expanded: fetch it.
            intent = self.stripe.PaymentIntent.retrieve(intent)
        intent_id, intent_status = (intent["id"], intent["status"]) if intent else (None, None)
        if session.get("status") == "expired":
            return PaymentState("EXPIRED", intent_id)
        if intent_status == "requires_capture":
            return PaymentState("AUTHORIZED", intent_id)
        if intent_status == "succeeded":
            return PaymentState("CAPTURED", intent_id)
        if intent_status == "canceled":
            return PaymentState("RELEASED", intent_id)
        return PaymentState("REQUIRES_ACTION", intent_id)

    def capture(self, provider_ref, payment_intent_ref, amount, key):
        intent = self.stripe.PaymentIntent.retrieve(payment_intent_ref)
        if intent.get("status") == "succeeded":
            return  # Already captured on an earlier attempt.
        self.stripe.PaymentIntent.capture(payment_intent_ref, amount_to_capture=cents(amount), idempotency_key=key)

    def release(self, provider_ref, payment_intent_ref, key):
        if payment_intent_ref:
            intent = self.stripe.PaymentIntent.retrieve(payment_intent_ref)
            if intent.get("status") == "requires_capture":
                self.stripe.PaymentIntent.cancel(payment_intent_ref, idempotency_key=key)
            return
        session = self.stripe.checkout.Session.retrieve(provider_ref)
        if session.get("status") == "open":
            self.stripe.checkout.Session.expire(provider_ref)

    def refund(self, payment_intent_ref, amount, key):
        if amount > 0:
            self.stripe.Refund.create(payment_intent=payment_intent_ref, amount=cents(amount), idempotency_key=key)

    def parse_webhook(self, payload: bytes, signature: str) -> dict:
        return self.stripe.Webhook.construct_event(payload, signature, settings.stripe_webhook_secret)


_provider: PaymentProvider | None = None
_lock = threading.Lock()


def get_payments() -> PaymentProvider:
    global _provider
    with _lock:
        if _provider is None:
            _provider = (StripePaymentProvider(settings.stripe_secret_key, settings.stripe_api_base)
                         if settings.payment_provider == "stripe" else SimulatedPaymentProvider())
        return _provider


def set_payments(provider: PaymentProvider | None) -> None:
    """Test hook."""
    global _provider
    with _lock:
        _provider = provider


def check_stripe() -> str:
    """Operator self-check for real Stripe test keys: create a manual-capture Checkout session and expire it.
    Run: docker compose exec api python -m app.payments"""
    if settings.payment_provider != "stripe":
        return "PAYMENT_PROVIDER is not 'stripe'; nothing to check."
    provider = StripePaymentProvider(settings.stripe_secret_key, settings.stripe_api_base)
    session = provider.authorize(order_id=f"selfcheck-{uuid.uuid4().hex[:8]}", amount=Decimal("1.00"), currency="NZD",
                                 description="CareTrip configuration check", success_url=settings.frontend_origin,
                                 cancel_url=settings.frontend_origin, key=f"selfcheck:{uuid.uuid4().hex}")
    provider.stripe.checkout.Session.expire(session.provider_ref)
    mode = "test" if settings.stripe_secret_key.startswith("sk_test_") else "LIVE"
    webhook = "set" if settings.stripe_webhook_secret else "missing (returns from Checkout still work; set it for reliability)"
    return f"Stripe {mode} key works: created and expired {session.provider_ref}. Webhook secret: {webhook}."


if __name__ == "__main__":
    print(check_stripe())
