"""The traveler's saved needs decide which access claims must be proven, and how offers rank."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.db import SEVERITY
from app.main import app
from app.skills.contracts import RankingInput, RequirementOutput
from app.skills.domain import assess_offer, compare_offers, required_claims, search_suppliers
from supplier_sim.catalog import CATALOG
from tests.helpers import advisor_login, create, get, login, new_email, postgres_available, wait_for
from tests.test_skills import supplier

LIFT, STEP, BATH = "lift_serves_all_guest_floors", "step_free_entry", "accessible_bathroom"
WHEELCHAIR = {"wheelchair": "MANUAL", "max_walk_meters": 100, "step_free": True, "accessible_bathroom": True,
              "dietary": ["GLUTEN_FREE"]}


def requirements(destination="Auckland", budget="1000"):
    return RequirementOutput(destination=destination, destination_scope="SUPPORTED", traveler_count=3, duration_days=3,
                             budget=Decimal(budget), currency="NZD", departure_date="2026-11-20", missing_fields=[])


def offer_verdicts(destination, claims):
    offers = search_suppliers(requirements(destination), supplier())
    return {o.product_id: min((a.verdict for a in assess_offer(o.evidence, claims).values()), key=SEVERITY.get)
            for o in offers}, offers


def test_claims_follow_the_words_and_the_saved_needs():
    assert required_claims(False, {}) == []
    assert required_claims(True, {}) == [LIFT, STEP]
    assert required_claims(False, {"accessible_bathroom": True}) == [BATH]
    assert required_claims(False, {"wheelchair": "SOMETIMES"}) == [LIFT]
    assert required_claims(False, {"wheelchair": "POWER"}) == [LIFT, STEP, BATH]


def test_a_wheelchair_user_needs_every_claim_proven():
    verdicts, _ = offer_verdicts("Auckland", required_claims(False, WHEELCHAIR))
    # C's lift and bathroom are both unproven; A is contradicted; only B proves all three.
    assert verdicts == {"PACKAGE_A": "BLOCK", "PACKAGE_C": "REVIEW", "PACKAGE_B": "PASS"}


@pytest.mark.parametrize("destination", list(CATALOG))
def test_every_destination_has_a_verified_stay_within_the_sample_budget(destination):
    verdicts, offers = offer_verdicts(destination, required_claims(True, WHEELCHAIR))
    assert {"PASS", "BLOCK"} <= set(verdicts.values())
    assert any(verdicts[o.product_id] == "PASS" and o.total_amount <= 1000 for o in offers)


def test_walking_limit_and_diet_shape_the_ranking():
    offers = search_suppliers(requirements("Queenstown", "2000"), supplier())
    plain = compare_offers(RankingInput(budget=Decimal(2000), offers=offers))
    assert "QTN_ALPINE" in plain.ordered_product_ids
    needs = compare_offers(RankingInput(budget=Decimal(2000), offers=offers, needs={"max_walk_meters": 150,
                                                                                     "dietary": ["VEGAN", "DIABETIC"]}))
    # A hillside chalet with a lot of walking is unsuitable for a 150 m limit.
    assert "QTN_ALPINE" not in needs.ordered_product_ids
    alpine = next(item for item in needs.ranked if item.product_id == "QTN_ALPINE")
    assert next(f for f in alpine.factors if f["factor"] == "pace")["code"] == "TOO_MUCH_WALKING"
    top = needs.ranked[0]
    assert top.product_id == "QTN_LAKEFRONT"
    assert next(f for f in top.factors if f["factor"] == "meals")["code"] == "DIET_2_OF_2"
    assert all(0 < item.score <= 100 for item in needs.ranked)


# --- Through the API ---------------------------------------------------------------------------

needs_api = pytest.mark.skipif(not postgres_available(), reason="Migrated PostgreSQL is unavailable")


def save_needs(client, needs, medical="Insulin in the fridge."):
    assert client.put("/api/auth/me/consent", json={"granted": True}).status_code == 200
    body = {"needs": {**needs, "medical_notes": medical}, "emergency_contact": {"name": "Ana", "phone": "021 555"}}
    assert client.put("/api/profile", json=body).status_code == 200


@needs_api
@pytest.mark.usefixtures("integration_mode")
def test_saved_needs_reach_the_trip_without_medical_notes():
    with TestClient(app) as client:
        owner = login(client)
        save_needs(client, WHEELCHAIR)
        # The request never mentions access: the saved profile supplies it.
        case_id = create(client, "Three travelers want a relaxed three-day Auckland trip. Budget NZD 1000.")
        assert wait_for(client, case_id, {"AWAITING_APPROVAL", "AWAITING_REVIEW", "HUMAN_REVIEW"})["status"] == "AWAITING_APPROVAL"
        case = get(client, f"/api/cases/{case_id}")
        saved = case["requirements"]["hard_constraints"]["needs"]
        assert saved == {key: WHEELCHAIR[key] for key in saved} and "medical_notes" not in saved
        offers = {o["product_id"]: o for o in get(client, f"/api/cases/{case_id}/offers")}
        assert offers["PACKAGE_B"]["label"] == "VERIFIED"
        assert offers["PACKAGE_B"]["claims"] == {LIFT: "PASS", STEP: "PASS", BATH: "PASS"}
        assert offers["PACKAGE_C"]["claims"] == {LIFT: "REVIEW", STEP: "PASS", BATH: "REVIEW"}
        assert next(f for f in offers["PACKAGE_B"]["ranking"]["factors"] if f["factor"] == "meals")["value"] == 1.0
        viewer = new_email()
        client.post(f"/api/cases/{case_id}/invitations", json={"email": viewer, "role": "VIEWER"})
        login(client, viewer)
        client.post(f"/api/invitations/{get(client, '/api/invitations')[0]['id']}", json={"accept": True})
        assert "needs" not in get(client, f"/api/cases/{case_id}")["requirements"]["hard_constraints"]
        login(client, owner)


@needs_api
@pytest.mark.usefixtures("integration_mode")
def test_each_unproven_claim_gets_its_own_review(override_settings):
    with TestClient(app) as client:
        owner = login(client)
        save_needs(client, {"wheelchair": "MANUAL"})
        # NZD 900 rules out B, so C's two unproven claims decide the trip.
        case_id = create(client, "Three travelers want a relaxed three-day Auckland trip. Budget NZD 900.")
        assert wait_for(client, case_id, {"AWAITING_REVIEW", "HUMAN_REVIEW"})["status"] == "AWAITING_REVIEW"
        advisor_login(client, override_settings)
        tasks = sorted((t for t in get(client, "/api/advisor/reviews") if t["case_id"] == case_id),
                       key=lambda t: t["claim_type"])
        assert [t["claim_type"] for t in tasks] == [BATH, LIFT]
        assert [e["reference"] for e in tasks[0]["evidence"]] == ["CAT-C-3"]
        first = client.post(f"/api/advisor/reviews/{tasks[0]['id']}", json={"decision": "PASS", "note": "Photos checked."})
        assert first.json()["data"]["case_resumed"] is False  # The lift is still open.
        second = client.post(f"/api/advisor/reviews/{tasks[1]['id']}", json={"decision": "PASS", "note": "Called."})
        assert second.json()["data"]["case_resumed"] is True
        login(client, owner)
        assert wait_for(client, case_id, {"AWAITING_APPROVAL", "HUMAN_REVIEW"})["status"] == "AWAITING_APPROVAL"
        offer = next(o for o in get(client, f"/api/cases/{case_id}/offers") if o["product_id"] == "PACKAGE_C")
        assert offer["label"] == "VERIFIED" and set(offer["claims"].values()) == {"PASS"}
