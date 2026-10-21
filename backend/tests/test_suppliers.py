"""The HTTP supplier client against the simulator: idempotency, error mapping, retries and the breaker."""
import httpx
import pytest
from starlette.testclient import TestClient

from app.suppliers import (CircuitBreaker, HoldExpired, HttpSupplierProvider, PriceChanged, SoldOut,
                           SupplierRejected, SupplierUnavailable)
from supplier_sim.app import app as simulator, reset


@pytest.fixture
def sim():
    reset()
    client = TestClient(simulator, base_url="http://supplier.local")
    yield client


def provider(client, **kwargs):
    return HttpSupplierProvider(client, "sim-local-key", backoff=0, **kwargs)


def fault(client, operation, mode, count=1):
    assert client.post("/admin/faults", headers={"X-Api-Key": "sim-local-key"},
                       json={"operation": operation, "mode": mode, "count": count}).status_code == 200


def offer_b(supplier):
    return next(o for o in supplier.search("Auckland", 3, 3, None) if o.product_id == "PACKAGE_B")


def test_hold_and_book_are_idempotent(sim):
    supplier = provider(sim)
    offer = offer_b(supplier)
    first = supplier.hold(offer.offer_ref, offer.total_amount, key="hold:order-1")
    again = supplier.hold(offer.offer_ref, offer.total_amount, key="hold:order-1")
    assert first.hold_ref == again.hold_ref
    booking = supplier.book(first.hold_ref, key="book:order-1")
    assert supplier.book(first.hold_ref, key="book:order-1").booking_ref == booking.booking_ref
    assert supplier.cancel(booking.booking_ref, key="cancel:order-1").status == "CANCELLED"


def test_supplier_errors_map_to_actionable_types(sim):
    supplier = provider(sim)
    offer = offer_b(supplier)
    fault(sim, "hold", "price_change")
    with pytest.raises(PriceChanged) as changed:
        supplier.hold(offer.offer_ref, offer.total_amount, key="hold:a")
    assert changed.value.new_total > offer.total_amount
    fault(sim, "hold", "sold_out")
    with pytest.raises(SoldOut):
        supplier.hold(offer.offer_ref, offer.total_amount, key="hold:b")
    fault(sim, "book", "reject")
    hold = supplier.hold(offer.offer_ref, offer.total_amount, key="hold:c")
    with pytest.raises(SupplierRejected):
        supplier.book(hold.hold_ref, key="book:c")
    with pytest.raises(HoldExpired):
        supplier.book("H-unknown", key="book:d")


def test_transient_outage_is_retried_then_succeeds(sim):
    supplier = provider(sim, retries=2)
    fault(sim, "search", "unavailable", count=2)
    assert len(supplier.search("Auckland", 3, 3, None)) == 3


def test_persistent_outage_raises_retryable_error(sim):
    supplier = provider(sim, retries=1)
    fault(sim, "search", "unavailable", count=5)
    with pytest.raises(SupplierUnavailable) as error:
        supplier.search("Auckland", 3, 3, None)
    assert error.value.retryable


def test_wrong_api_key_is_rejected(sim):
    supplier = HttpSupplierProvider(sim, "wrong-key", backoff=0)
    with pytest.raises(SupplierRejected):
        supplier.search("Auckland", 3, 3, None)


def test_network_errors_open_the_circuit():
    def broken(request):
        raise httpx.ConnectError("refused")
    supplier = HttpSupplierProvider(httpx.Client(transport=httpx.MockTransport(broken), base_url="http://x"),
                                    "k", retries=0, backoff=0)
    supplier.breaker = CircuitBreaker(threshold=2, cooldown=60)
    for _ in range(2):
        with pytest.raises(SupplierUnavailable):
            supplier.search("Auckland", 3, 3, None)
    with pytest.raises(SupplierUnavailable, match="circuit is open"):
        supplier.search("Auckland", 3, 3, None)
