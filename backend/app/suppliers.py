"""Supplier integration: one interface, one HTTP client.

Every supplier write carries an Idempotency-Key derived from our own record IDs, so retrying after a
timeout can never create a second hold or booking. Errors are mapped to a small set of types the
workflow can act on.
"""

import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol

import httpx

from app.config import settings


class SupplierError(Exception):
    code = "SUPPLIER_ERROR"
    retryable = False


class SupplierUnavailable(SupplierError):
    code, retryable = "SUPPLIER_UNAVAILABLE", True


class SoldOut(SupplierError):
    code = "SOLD_OUT"


class PriceChanged(SupplierError):
    code = "PRICE_CHANGED"

    def __init__(self, new_total: Decimal):
        super().__init__(f"Supplier price changed to {new_total}")
        self.new_total = new_total


class HoldExpired(SupplierError):
    code = "HOLD_EXPIRED"


class SupplierRejected(SupplierError):
    code = "SUPPLIER_REJECTED"


@dataclass(frozen=True)
class SupplierEvidence:
    claim_type: str
    source: str
    polarity: str
    strength: str
    reference: str
    detail: str
    url: str


@dataclass(frozen=True)
class SupplierOffer:
    offer_ref: str
    product_id: str
    name: str
    total_amount: Decimal
    currency: str
    includes: list[str]
    attributes: dict
    cancellation_policy: list[dict]
    valid_until: datetime
    evidence: list[SupplierEvidence] = field(default_factory=list)


@dataclass(frozen=True)
class Hold:
    hold_ref: str
    total_amount: Decimal
    expires_at: datetime


@dataclass(frozen=True)
class Booking:
    booking_ref: str
    status: str


class SupplierProvider(Protocol):
    name: str

    def search(self, destination: str, travelers: int, duration_days: int, start_date: date | None) -> list[SupplierOffer]: ...
    def hold(self, offer_ref: str, expected_total: Decimal, key: str) -> Hold: ...
    def book(self, hold_ref: str, key: str) -> Booking: ...
    def cancel(self, booking_ref: str, key: str) -> Booking: ...


class CircuitBreaker:
    """Fail fast for a cool-down period after repeated outages, instead of piling up slow calls."""

    def __init__(self, threshold: int = 5, cooldown: float = 30.0):
        self.threshold, self.cooldown = threshold, cooldown
        self.failures, self.opened_at = 0, 0.0
        self._lock = threading.Lock()

    def check(self) -> None:
        with self._lock:
            if self.failures >= self.threshold and time.monotonic() - self.opened_at < self.cooldown:
                raise SupplierUnavailable("Supplier circuit is open")

    def record(self, ok: bool) -> None:
        with self._lock:
            if ok:
                self.failures = 0
            else:
                self.failures += 1
                if self.failures >= self.threshold:
                    self.opened_at = time.monotonic()


class HttpSupplierProvider:
    name = "http"

    def __init__(self, client: httpx.Client, api_key: str, retries: int = 2, backoff: float = 0.2):
        self.client, self.api_key = client, api_key
        self.retries, self.backoff = retries, backoff
        self.breaker = CircuitBreaker()

    def _request(self, method: str, path: str, *, key: str | None = None, **kwargs) -> dict:
        self.breaker.check()
        headers = {"X-Api-Key": self.api_key}
        if key:
            headers["Idempotency-Key"] = key
        last: Exception | None = None
        # GETs and keyed writes are safe to repeat.
        for attempt in range(self.retries + 1):
            try:
                response = self.client.request(method, path, headers=headers, **kwargs)
            except httpx.TransportError as exc:
                last = SupplierUnavailable(f"Supplier unreachable: {type(exc).__name__}")
            else:
                if response.status_code < 500:
                    self.breaker.record(True)
                    return self._result(response)
                last = SupplierUnavailable(f"Supplier error {response.status_code}")
            self.breaker.record(False)
            if attempt < self.retries:
                time.sleep(self.backoff * (2 ** attempt))
        raise last

    @staticmethod
    def _result(response: httpx.Response) -> dict:
        body = response.json() if response.content else {}
        if response.is_success:
            return body
        detail = body.get("detail", {}) if isinstance(body, dict) else {}
        code = detail.get("code") if isinstance(detail, dict) else None
        if code == "SOLD_OUT":
            raise SoldOut(detail.get("message", "Sold out"))
        if code == "PRICE_CHANGED":
            raise PriceChanged(Decimal(detail["new_total"]))
        if code in {"HOLD_EXPIRED", "HOLD_NOT_FOUND"}:
            raise HoldExpired(detail.get("message", "Hold expired"))
        raise SupplierRejected(f"Supplier rejected the request ({response.status_code} {code})")

    def search(self, destination, travelers, duration_days, start_date):
        params = {"destination": destination, "travelers": travelers, "duration_days": duration_days}
        if start_date:
            params["start_date"] = start_date.isoformat()
        body = self._request("GET", "/v1/offers", params=params)
        return [SupplierOffer(
            offer_ref=item["offer_ref"], product_id=item["product_id"], name=item["name"],
            total_amount=Decimal(item["total_amount"]), currency=item["currency"], includes=item["includes"],
            attributes=item["attributes"], cancellation_policy=item["cancellation_policy"],
            valid_until=datetime.fromisoformat(item["valid_until"]),
            evidence=[SupplierEvidence(**evidence) for evidence in item["evidence"]],
        ) for item in body["offers"]]

    def hold(self, offer_ref, expected_total, key):
        body = self._request("POST", "/v1/holds", key=key,
                             json={"offer_ref": offer_ref, "expected_total": str(expected_total)})
        return Hold(body["hold_ref"], Decimal(body["total_amount"]), datetime.fromisoformat(body["expires_at"]))

    def book(self, hold_ref, key):
        body = self._request("POST", "/v1/bookings", key=key, json={"hold_ref": hold_ref})
        return Booking(body["booking_ref"], body["status"])

    def cancel(self, booking_ref, key):
        body = self._request("POST", f"/v1/bookings/{booking_ref}/cancel", key=key)
        return Booking(body["booking_ref"], body["status"])


_provider: SupplierProvider | None = None
_provider_lock = threading.Lock()


def get_supplier() -> SupplierProvider:
    """The configured supplier. Without SUPPLIER_BASE_URL the simulator runs in-process (development)."""
    global _provider
    with _provider_lock:
        if _provider is None:
            if settings.supplier_base_url:
                client = httpx.Client(base_url=settings.supplier_base_url, timeout=httpx.Timeout(5.0, connect=2.0))
            else:
                from starlette.testclient import TestClient
                from supplier_sim.app import app as simulator
                client = TestClient(simulator, base_url="http://supplier.local")
            _provider = HttpSupplierProvider(client, settings.supplier_api_key)
        return _provider


def set_supplier(provider: SupplierProvider | None) -> None:
    """Test hook."""
    global _provider
    with _provider_lock:
        _provider = provider
