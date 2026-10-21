"""Signing in by text message, for accounts that verified a mobile number."""

import random

import pytest
from fastapi.testclient import TestClient

from app.auth import normalize_phone
from app.main import app
from tests.helpers import get, login, postgres_available

pytestmark = [pytest.mark.skipif(not postgres_available(), reason="Migrated PostgreSQL is unavailable"),
              pytest.mark.usefixtures("integration_mode")]


def new_mobile():
    return f"021 {random.randint(100, 999)} {random.randint(1000, 9999)}"


def test_numbers_are_stored_in_international_form():
    assert normalize_phone("021 555 0100") == "+64215550100"
    assert normalize_phone("+64 (21) 555-0100") == "+64215550100"
    assert normalize_phone("0061 412 345 678") == "+61412345678"
    with pytest.raises(ValueError):
        normalize_phone("12345")


def add_phone(client, mobile):
    code = client.put("/api/auth/me/phone", json={"phone": mobile}).json()["data"]["dev_code"]
    return client.post("/api/auth/me/phone/verify", json={"phone": mobile, "code": code})


def test_a_verified_number_signs_in_to_its_own_account_only():
    with TestClient(app) as client:
        login(client)
        me = get(client, "/api/auth/me")
        mobile = new_mobile()
        code = client.put("/api/auth/me/phone", json={"phone": mobile}).json()["data"]["dev_code"]
        wrong = "000000" if code != "000000" else "111111"
        assert client.post("/api/auth/me/phone/verify", json={"phone": mobile, "code": wrong}).status_code == 400
        assert client.post("/api/auth/me/phone/verify", json={"phone": mobile, "code": code}).status_code == 200
        assert get(client, "/api/auth/me")["phone"] == normalize_phone(mobile)
        # Another account cannot claim the same number.
        login(client)
        assert add_phone(client, mobile).json()["error"]["code"] == "PHONE_TAKEN"
        client.cookies.clear()
        sent = client.post("/api/auth/request-code", json={"phone": mobile}).json()["data"]
        verified = client.post("/api/auth/verify", json={"phone": mobile, "code": sent["dev_code"]})
        assert verified.status_code == 200 and verified.json()["data"]["id"] == me["id"]


def test_unknown_numbers_get_the_same_answer_and_cannot_create_accounts():
    with TestClient(app) as client:
        response = client.post("/api/auth/request-code", json={"phone": new_mobile()})
        assert response.status_code == 202 and response.json()["data"]["sent"] is True
        assert "dev_code" not in response.json()["data"]
        assert client.post("/api/auth/request-code", json={}).status_code == 400
        assert client.post("/api/auth/request-code", json={"email": "a@b.test", "phone": "021 555 0100"}).status_code == 400


def test_a_removed_number_no_longer_signs_in():
    with TestClient(app) as client:
        login(client)
        mobile = new_mobile()
        add_phone(client, mobile)
        code = client.post("/api/auth/request-code", json={"phone": mobile}).json()["data"]["dev_code"]
        assert client.delete("/api/auth/me/phone").status_code == 200
        assert client.post("/api/auth/verify", json={"phone": mobile, "code": code}).status_code == 400
