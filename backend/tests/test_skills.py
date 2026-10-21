from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.skills.contracts import DraftPlanInput, RankingInput, RequirementInput, RequirementOutput, ReviewInput
from app.skills.domain import (
    build_draft_itinerary, compare_offers, extract_requirements, generate_review, rerank_offers,
    search_suppliers, validate_requirements, verify_evidence, normalize_currency, assess_offer,
)
from app.skills.destinations import resolve_attractions, resolve_destination


def complete_requirements():
    return extract_requirements(RequirementInput(
        request="Three travelers, three days in Auckland, lift required, budget NZD 1000.",
        demo_date=date(2026, 10, 16),
    ))


def test_requirement_schema_and_extraction():
    with pytest.raises(ValidationError):
        RequirementInput(request="short")
    result = complete_requirements()
    assert result.missing_fields == []
    assert result.budget == Decimal("1000")
    assert result.elevator_required is True
    assert result.departure_date == date(2026, 10, 16)


def test_missing_fields_never_filled_silently():
    result = extract_requirements(RequirementInput(request="Auckland trip for three travelers"))
    assert "departure_date" in result.missing_fields
    assert "currency" in result.missing_fields
    assert "duration_days" in result.missing_fields
    with pytest.raises(ValueError):
        search_suppliers(result, supplier())


def supplier():
    from starlette.testclient import TestClient
    from app.suppliers import HttpSupplierProvider
    from supplier_sim.app import app as simulator, reset

    reset()
    return HttpSupplierProvider(TestClient(simulator, base_url="http://supplier.local"), "sim-local-key", backoff=0)


def ranking_input(budget="1000", elevator=True, pace="RELAXED"):
    offers = search_suppliers(complete_requirements(), supplier())
    return RankingInput(budget=Decimal(budget), offers=offers, elevator_required=elevator, travel_pace=pace)


def test_supplier_offers_are_priced_for_the_party_and_carry_evidence():
    offers = search_suppliers(complete_requirements(), supplier())
    assert [(item.product_id, item.total_amount) for item in offers] == [
        ("PACKAGE_A", Decimal("820.00")), ("PACKAGE_C", Decimal("880.00")), ("PACKAGE_B", Decimal("920.00"))]
    assert all(item.supplier_offer_ref and item.cancellation_policy and item.evidence for item in offers)
    bigger = complete_requirements().model_copy(update={"traveler_count": 2, "duration_days": 6})
    assert search_suppliers(bigger, supplier())[0].total_amount == Decimal("1093.33")  # 820 * 12 / 9


def test_multi_factor_ranking_explains_itself():
    result = compare_offers(ranking_input())
    # B has a lift and step-free entry, low walking and gentle cancellation terms: it outranks cheaper A.
    assert result.ordered_product_ids == ["PACKAGE_B", "PACKAGE_C", "PACKAGE_A"]
    top = result.ranked[0]
    assert {factor["factor"] for factor in top.factors} == {"accessibility", "price", "pace", "flexibility", "rating"}
    assert next(f for f in top.factors if f["factor"] == "accessibility")["code"] == "LIFT_YES_STEP_FREE_YES"
    assert 0 < top.score <= 100


def test_without_an_access_need_no_offer_is_penalised_for_access():
    def score_of(result, product):
        return next(item for item in result.ranked if item.product_id == product)
    with_need = score_of(compare_offers(ranking_input()), "PACKAGE_A")
    without = score_of(compare_offers(ranking_input(elevator=False, pace="STANDARD")), "PACKAGE_A")
    access = next(f for f in without.factors if f["factor"] == "accessibility")
    assert (access["code"], access["value"]) == ("NO_ACCESS_NEED", 1.0)
    assert without.score > with_need.score


def test_rerank_excludes_blocked_and_unsettled_offers():
    reranked = rerank_offers(ranking_input(), {"PACKAGE_A": "BLOCK", "PACKAGE_C": "REVIEW"})
    assert reranked.ordered_product_ids == ["PACKAGE_B"]
    assert {item.product_id for item in reranked.ranked if not item.eligible} == {"PACKAGE_A", "PACKAGE_C"}


def test_evidence_conflict_review_and_pass():
    offers = {item.product_id: item for item in search_suppliers(complete_requirements(), supplier())}
    lift = "lift_serves_all_guest_floors"
    verdicts = {product: verify_evidence(offer.evidence, lift).verdict for product, offer in offers.items()}
    assert verdicts == {"PACKAGE_A": "BLOCK", "PACKAGE_C": "REVIEW", "PACKAGE_B": "PASS"}
    assert {item.polarity for item in offers["PACKAGE_A"].evidence if item.claim_type == lift} == {"SUPPORT", "CONTRADICT"}
    assert all(item.url for offer in offers.values() for item in offer.evidence)
    # Without an access need nothing has to be proven.
    assert assess_offer(offers["PACKAGE_A"].evidence, [])["no_access_need"].verdict == "PASS"


def test_budget_and_currency_guard():
    assert compare_offers(ranking_input(budget="900")).ordered_product_ids == ["PACKAGE_C", "PACKAGE_A"]
    unsupported = RequirementOutput(destination="Auckland", departure_date=date(2026, 10, 16),
                                    traveler_count=3, duration_days=3, budget=Decimal("1000"), currency="USD")
    assert "currency" in validate_requirements(unsupported)


def test_review_summarises_the_confirmed_order():
    result = generate_review(ReviewInput(case_id="case", offer_id="offer", order_id="order"))
    assert result.status == "BOOKED"
    assert "Order order" in result.summary and "confirmed" in result.summary


@pytest.mark.parametrize("phrase,destination", [
    ("奥克兰三日游", "Auckland"), ("Queenstown trip", "Queenstown"),
    ("罗托鲁瓦三日游", "Rotorua"), ("Wellington trip", "Wellington"),
    ("基督城三日游", "Christchurch"), ("陶波三日游", "Taupō"),
])
def test_supported_destination_aliases(phrase, destination):
    assert resolve_destination(phrase) == (destination, "SUPPORTED")


def test_queenstown_attractions_and_relaxed_pace():
    result = extract_requirements(RequirementInput(
        request="我想和两个朋友去皇后镇玩三天，想看看瓦卡蒂普湖，坐坐缆车，不想太累。"))
    assert result.destination == "Queenstown"
    assert result.destination_scope == "SUPPORTED"
    assert result.traveler_count == 3
    assert result.duration_days == 3
    assert result.travel_pace == "RELAXED"
    assert result.attractions == ["Lake Wakatipu", "Skyline Queenstown"]
    assert "budget" in result.missing_fields


@pytest.mark.parametrize("travel_text", [
    "我想和两个朋友去奥克兰玩三天，预算 NZD 1000。",
    "我想和两个朋友去奥克兰玩三天，预算 N\u200bZD 1000。",
    "我想和两个朋友去奥克兰玩三天，预算纽币1000元。",
])
def test_chinese_nzd_is_canonical(travel_text):
    result = extract_requirements(RequirementInput(request=travel_text, demo_date=date(2026, 10, 16)))
    assert result.destination == "Auckland"
    assert result.traveler_count == 3
    assert result.duration_days == 3
    assert result.budget == Decimal("1000")
    assert result.currency == "NZD"
    assert result.missing_fields == []


def test_gemini_adapter_validates_structured_output(monkeypatch):
    from types import SimpleNamespace
    from app.skills import model_adapter

    monkeypatch.setenv("GEMINI_API_KEY", "test-only-value")
    response = SimpleNamespace(text='{"destination":"Queenstown","traveler_count":3,"duration_days":3,'
                                    '"budget":1000,"currency":" nzd ","elevator_required":false}',
                               usage_metadata=SimpleNamespace(prompt_token_count=14, candidates_token_count=20))
    fake = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **_: response))
    monkeypatch.setattr(model_adapter.genai, "Client", lambda **_: fake)
    result, usage = model_adapter._extract_with_gemini(RequirementInput(
        request="Three travelers in Queenstown for three days with NZD 1000", demo_date=date(2026, 10, 16)))
    assert (result.destination, result.currency, result.missing_fields) == ("Queenstown", "NZD", [])
    assert usage == {"input_tokens": 14, "output_tokens": 20}


def test_clarified_currency_is_normalized():
    assert normalize_currency(" n\u200bzd ") == "NZD"


def test_gemini_invalid_output_raises_without_mock_fallback(monkeypatch):
    from types import SimpleNamespace
    from app.skills import model_adapter

    monkeypatch.setenv("GEMINI_API_KEY", "test-only-value")
    fake = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **_: SimpleNamespace(text='{"budget":-5}')))
    monkeypatch.setattr(model_adapter.genai, "Client", lambda **_: fake)
    with pytest.raises(ValidationError):
        model_adapter._extract_with_gemini(RequirementInput(request="Auckland trip on a budget"))


def test_foreign_destination_never_reaches_supplier_discovery():
    result = extract_requirements(RequirementInput(
        request="Three travelers want three days in Tokyo, budget NZD 1000."))
    assert result.destination_scope == "OUTSIDE_NZ"
    assert result.destination is None
    with pytest.raises(ValueError):
        search_suppliers(result, supplier())


def test_mixed_new_zealand_and_foreign_request_is_outside_scope():
    assert resolve_destination("Three days in Auckland and Tokyo") == (None, "OUTSIDE_NZ")


def test_unknown_attraction_does_not_match_unrelated_photo():
    assert resolve_attractions("Queenstown trip to a mystery place", "Queenstown") == []


def test_chinese_per_person_budget_is_totalled_only_with_traveler_count():
    result = extract_requirements(RequirementInput(request="我和两个朋友去奥克兰玩三天，预算每人1000纽币。"))
    assert result.budget == Decimal("3000")
    assert result.currency == "NZD"


def test_draft_days_use_only_extracted_queenstown_places():
    days = build_draft_itinerary(DraftPlanInput(
        destination="Queenstown", destination_scope="SUPPORTED", duration_days=3,
        attractions=["Lake Wakatipu", "Skyline Queenstown"], travel_pace="RELAXED"))
    assert [day.attraction for day in days] == ["Lake Wakatipu", "Skyline Queenstown", None]
    assert len({day.title for day in days}) == 3
    assert all(day.status == "ILLUSTRATIVE_DRAFT" for day in days)
    assert all(day.activities and day.rest_note and day.verification_notes for day in days)


def test_foreign_destination_has_no_draft_days():
    assert build_draft_itinerary(DraftPlanInput(
        destination=None, destination_scope="OUTSIDE_NZ", duration_days=3)) == []


def test_chinese_request_with_full_width_comma_after_currency_parses():
    # Regression: NFKC turns "，" into ",", which the budget pattern used to take as the amount.
    result = extract_requirements(RequirementInput(
        request="我们三个人想去奥克兰轻松玩三天，总预算 1000 纽币，需要能到所有客房楼层的电梯。",
        demo_date=date(2026, 11, 20)))
    assert (result.destination, result.traveler_count, result.duration_days) == ("Auckland", 3, 3)
    assert result.budget == Decimal("1000") and result.currency == "NZD"
    assert result.elevator_required is True and result.travel_pace == "RELAXED"
    assert result.missing_fields == []


def test_currency_word_without_amount_leaves_budget_missing():
    result = extract_requirements(RequirementInput(request="三个人去奥克兰三天，用纽币，预算待定。",
                                                   demo_date=date(2026, 11, 20)))
    assert result.budget is None and "budget" in result.missing_fields


def test_draft_itinerary_follows_the_case_language():
    data = dict(destination="Auckland", destination_scope="SUPPORTED", duration_days=2,
                attractions=["Sky Tower"], travel_pace="RELAXED")
    english = build_draft_itinerary(DraftPlanInput(**data))
    chinese = build_draft_itinerary(DraftPlanInput(**data, language="zh"))
    assert [day.attraction for day in english] == [day.attraction for day in chinese]
    assert english[0].title == "Explore Sky Tower" and chinese[0].title == "游览天空塔"
    assert "休息" in chinese[0].rest_note and "确认" in chinese[0].verification_notes[0]


@pytest.mark.parametrize("days_before, percent", [(30, 100), (14, 100), (10, 100), (7, 100), (5, 50), (2, 50), (1, 0)])
def test_refund_follows_the_offer_policy(days_before, percent):
    from datetime import timedelta
    from app.skills.domain import refund_percent

    policy = [{"days_before": 7, "refund_percent": 100}, {"days_before": 2, "refund_percent": 50}]
    today = date(2026, 11, 1)
    assert refund_percent(policy, today + timedelta(days=days_before), today) == percent
    assert refund_percent([], today + timedelta(days=30), today) == 0


def test_the_rule_based_outline_follows_mobility_needs():
    from app.skills.contracts import DraftPlanInput as Draft

    base = dict(destination="Queenstown", destination_scope="SUPPORTED", duration_days=2, travel_pace="STANDARD")
    plain = build_draft_itinerary(Draft(**base))
    assert {day.intensity for day in plain} == {"MODERATE"}
    assisted = build_draft_itinerary(Draft(**base, access_needs={"wheelchair": "MANUAL"}))
    assert {day.intensity for day in assisted} == {"LOW"}
    assert all("step-free access" in day.verification_notes[0] for day in assisted)
    walking = build_draft_itinerary(Draft(**base, access_needs={"max_walk_meters": 200}, language="zh"))
    assert "无台阶通道" in walking[0].verification_notes[0]
