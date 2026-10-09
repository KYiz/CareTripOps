from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.skills.contracts import DraftPlanInput, RankingInput, RequirementInput, RequirementOutput, ReviewInput
from app.skills.domain import (
    build_draft_itinerary, compare_offers, extract_requirements, generate_review, rerank_offers,
    search_suppliers, validate_requirements, verify_evidence, normalize_currency,
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
        search_suppliers(result)


def test_supplier_comparison_and_rerank():
    requirements = complete_requirements()
    offers = search_suppliers(requirements)
    assert [(item.product_id, item.total_amount) for item in offers] == [
        ("PACKAGE_A", Decimal("820.00")), ("PACKAGE_C", Decimal("880.00")),
        ("PACKAGE_B", Decimal("920.00")),
    ]
    ranking = RankingInput(budget=requirements.budget, offers=offers)
    assert compare_offers(ranking).ordered_product_ids == ["PACKAGE_A", "PACKAGE_C", "PACKAGE_B"]
    reranked = rerank_offers(ranking, {"PACKAGE_A": "BLOCK", "PACKAGE_C": "REVIEW"})
    assert reranked.ordered_product_ids == ["PACKAGE_B"]


def test_evidence_conflict_review_and_pass():
    a_sources, a = verify_evidence("PACKAGE_A", True)
    c_sources, c = verify_evidence("PACKAGE_C", True)
    b_sources, b = verify_evidence("PACKAGE_B", True)
    assert (a.verdict, c.verdict, b.verdict) == ("BLOCK", "REVIEW", "PASS")
    assert len(a_sources) == 3 and len(c_sources) == 1 and len(b_sources) == 1
    assert {item.polarity for item in a_sources} == {"SUPPORT", "CONTRADICT"}
    assert all(item.reference for item in a_sources + c_sources + b_sources)


def test_budget_and_currency_guard():
    offers = search_suppliers(complete_requirements())
    assert compare_offers(RankingInput(budget=Decimal("900"), offers=offers)).ordered_product_ids == [
        "PACKAGE_A", "PACKAGE_C",
    ]
    unsupported = RequirementOutput(destination="Auckland", departure_date=date(2026, 10, 16),
                                    traveler_count=3, duration_days=3, budget=Decimal("1000"), currency="USD")
    assert "currency" in validate_requirements(unsupported)


def test_review_is_explicitly_simulated():
    result = generate_review(ReviewInput(case_id="case", offer_id="offer", order_id="order"))
    assert result.status == "DEMO_COMPLETED"
    assert "Simulated order" in result.summary


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
        search_suppliers(result)


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
