"""A stand-in travel supplier with the behaviours a real one has: limited inventory, holds that expire,
price changes, rejections, outages and idempotent writes. CareTrip talks to it over HTTP exactly as it
would talk to a real supplier, so swapping in a real provider only replaces the client.

Run: uvicorn supplier_sim.app:app --port 9000. All data is synthetic and held in memory.
"""

import os
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from supplier_sim.catalog import CATALOG, evidence_rows

API_KEY = os.getenv("SUPPLIER_API_KEY", "sim-local-key")
HOLD_MINUTES = int(os.getenv("SUPPLIER_HOLD_MINUTES", "20"))
INVENTORY_PER_DATE = int(os.getenv("SUPPLIER_INVENTORY_PER_DATE", "50"))
REFERENCE_PARTY = Decimal(9)  # Catalogue prices are quoted for 3 travelers x 3 days.

_lock = threading.Lock()
_state: dict = {}


def reset() -> None:
    with _lock:
        _state.clear()
        _state.update({"holds": {}, "bookings": {}, "sold": {}, "idempotency": {}, "faults": []})


reset()
app = FastAPI(title="CareTrip supplier simulator", docs_url=None, redoc_url=None, openapi_url=None)


def now() -> datetime:
    return datetime.now(timezone.utc)


def problem(status: int, code: str, message: str, **extra):
    raise HTTPException(status_code=status, detail={"code": code, "message": message, **extra})


@app.middleware("http")
async def authenticate(request: Request, call_next):
    from fastapi.responses import JSONResponse
    if request.url.path.startswith(("/v1/", "/admin/")) and request.headers.get("x-api-key") != API_KEY:
        return JSONResponse(status_code=401, content={"detail": {"code": "UNAUTHORIZED", "message": "Bad API key"}})
    return await call_next(request)


def _fault(operation: str) -> str | None:
    """Consume the next injected fault that applies to this operation, if any."""
    with _lock:
        for fault in _state["faults"]:
            if fault["operation"] in (operation, "*") and fault["remaining"] > 0:
                fault["remaining"] -= 1
                return fault["mode"]
    return None


def _apply_fault(operation: str):
    mode = _fault(operation)
    if mode == "unavailable":
        problem(503, "UNAVAILABLE", "Supplier temporarily unavailable")
    if mode == "reject":
        problem(422, "REJECTED", "Supplier declined the request")
    return mode


def _price(base_total: str, travelers: int, days: int) -> Decimal:
    return (Decimal(base_total) * travelers * days / REFERENCE_PARTY).quantize(Decimal("0.01"), ROUND_HALF_UP)


def _product(product_id: str) -> tuple[str, dict]:
    for destination, products in CATALOG.items():
        for product in products:
            if product["product_id"] == product_id:
                return destination, product
    problem(404, "NOT_FOUND", "Unknown product")


def _offer_ref(product_id: str, travelers: int, days: int, start: date) -> str:
    return f"{product_id}:{travelers}:{days}:{start.isoformat()}"


def _parse_ref(offer_ref: str) -> tuple[str, int, int, date]:
    try:
        product_id, travelers, days, start = offer_ref.split(":")
        return product_id, int(travelers), int(days), date.fromisoformat(start)
    except ValueError:
        problem(400, "BAD_OFFER_REF", "Malformed offer reference")


def _idempotent(key: str | None, operation: str, compute):
    if not key:
        problem(400, "IDEMPOTENCY_KEY_REQUIRED", "Writes require an Idempotency-Key header")
    with _lock:
        cached = _state["idempotency"].get((operation, key))
    if cached is not None:
        return cached
    result = compute()
    with _lock:
        _state["idempotency"].setdefault((operation, key), result)
        return _state["idempotency"][(operation, key)]


@app.get("/v1/offers")
def search(destination: str, travelers: int = Query(ge=1, le=12), duration_days: int = Query(ge=1, le=21),
           start_date: date | None = None):
    _apply_fault("search")
    start = start_date or (date.today() + timedelta(days=14))
    offers = []
    for product in CATALOG.get(destination, []):
        offers.append({
            "offer_ref": _offer_ref(product["product_id"], travelers, duration_days, start),
            "product_id": product["product_id"], "name": product["name"], "destination": destination,
            "total_amount": str(_price(product["base_total"], travelers, duration_days)), "currency": "NZD",
            "includes": product["includes"], "attributes": product["attributes"],
            "cancellation_policy": product["cancellation_policy"],
            "valid_until": (now() + timedelta(days=7)).isoformat(),
            "evidence": evidence_rows(product),
        })
    return {"offers": offers}


class HoldRequest(BaseModel):
    offer_ref: str
    expected_total: Decimal


@app.post("/v1/holds", status_code=201)
def hold(body: HoldRequest, idempotency_key: str | None = Header(default=None)):
    def compute():
        mode = _apply_fault("hold")
        product_id, travelers, days, start = _parse_ref(body.offer_ref)
        _, product = _product(product_id)
        price = _price(product["base_total"], travelers, days)
        if mode == "price_change":
            price = (price * Decimal("1.08")).quantize(Decimal("0.01"))
        if price != body.expected_total:
            problem(409, "PRICE_CHANGED", "The supplier price changed", new_total=str(price))
        with _lock:
            sold_key = (product_id, start.isoformat())
            if mode == "sold_out" or _state["sold"].get(sold_key, 0) >= INVENTORY_PER_DATE:
                problem(409, "SOLD_OUT", "No inventory left for this date")
            _state["sold"][sold_key] = _state["sold"].get(sold_key, 0) + 1
            hold_ref = f"H-{uuid.uuid4().hex[:12]}"
            record = {"hold_ref": hold_ref, "offer_ref": body.offer_ref, "total_amount": str(price), "currency": "NZD",
                      "expires_at": (now() + timedelta(minutes=HOLD_MINUTES)).isoformat(), "status": "HELD"}
            _state["holds"][hold_ref] = record
            return dict(record)
    return _idempotent(idempotency_key, "hold", compute)


class BookingRequest(BaseModel):
    hold_ref: str


@app.post("/v1/bookings", status_code=201)
def book(body: BookingRequest, idempotency_key: str | None = Header(default=None)):
    def compute():
        _apply_fault("book")
        with _lock:
            held = _state["holds"].get(body.hold_ref)
            if not held:
                problem(404, "HOLD_NOT_FOUND", "Unknown hold")
            if held["status"] != "HELD" or datetime.fromisoformat(held["expires_at"]) <= now():
                held["status"] = "EXPIRED"
                problem(410, "HOLD_EXPIRED", "The hold expired before confirmation")
            held["status"] = "BOOKED"
            booking_ref = f"B-{uuid.uuid4().hex[:12]}"
            record = {"booking_ref": booking_ref, "hold_ref": body.hold_ref, "offer_ref": held["offer_ref"],
                      "total_amount": held["total_amount"], "currency": "NZD", "status": "CONFIRMED"}
            _state["bookings"][booking_ref] = record
            return dict(record)
    return _idempotent(idempotency_key, "book", compute)


@app.post("/v1/bookings/{booking_ref}/cancel")
def cancel(booking_ref: str, idempotency_key: str | None = Header(default=None)):
    def compute():
        _apply_fault("cancel")
        with _lock:
            booking = _state["bookings"].get(booking_ref)
            if not booking:
                problem(404, "BOOKING_NOT_FOUND", "Unknown booking")
            booking["status"] = "CANCELLED"
            return dict(booking)
    return _idempotent(idempotency_key, "cancel", compute)


@app.get("/v1/bookings/{booking_ref}")
def booking(booking_ref: str):
    with _lock:
        record = _state["bookings"].get(booking_ref)
    if not record:
        problem(404, "BOOKING_NOT_FOUND", "Unknown booking")
    return record


class Fault(BaseModel):
    operation: str = Field(pattern="^(search|hold|book|cancel|\\*)$")
    mode: str = Field(pattern="^(unavailable|reject|price_change|sold_out)$")
    count: int = Field(default=1, ge=1, le=100)


@app.post("/admin/faults")
def inject(fault: Fault):
    """Test hook: make the next `count` calls of an operation fail in the given way."""
    with _lock:
        _state["faults"].append({"operation": fault.operation, "mode": fault.mode, "remaining": fault.count})
    return {"ok": True}


@app.post("/admin/reset")
def admin_reset():
    reset()
    return {"ok": True}
