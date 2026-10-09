from datetime import date

import pytest

from app.skills.contracts import DraftPlanInput, RequirementInput
from app.skills.domain import build_draft_itinerary, extract_requirements, infer_interest_tags
from app.two_brains import ModelDay, ModelPlan, deterministic_findings, validate_plan


@pytest.mark.parametrize("travel_text,expected_destination,days,first_place", [
    ("我和两个朋友去皇后镇玩三天，预算NZD1000，想看湖景和坐缆车，不想太累。",
     "Queenstown", 3, "Lake Wakatipu"),
    ("两人去罗托鲁瓦玩两天，预算NZD800，想体验温泉，轻松一点。",
     "Rotorua", 2, "Polynesian Spa"),
    ("三人去奥克兰三天，预算NZD1000，想看城市与文化。",
     "Auckland", 3, "Auckland War Memorial Museum"),
    ("两人去陶波两天，预算NZD800，喜欢自然风景。",
     "Taupō", 2, "Lake Taupō"),
])
def test_distinct_complete_local_outlines(travel_text, expected_destination, days, first_place):
    requirements = extract_requirements(RequirementInput(request=travel_text, demo_date=date(2026, 10, 20)))
    assert requirements.destination == expected_destination
    assert requirements.duration_days == days
    assert requirements.currency == "NZD"
    outline = build_draft_itinerary(DraftPlanInput(
        destination=requirements.destination, destination_scope=requirements.destination_scope,
        duration_days=requirements.duration_days, attractions=requirements.attractions,
        travel_pace=requirements.travel_pace, interest_tags=infer_interest_tags(travel_text)))
    assert len(outline) == days
    assert outline[0].attraction == first_place
    assert len({day.title for day in outline}) == days
    assert len({day.attraction for day in outline if day.attraction}) == len([day for day in outline if day.attraction])
    assert all(day.activities and day.rest_note and day.verification_notes for day in outline)
    assert all(day.status == "ILLUSTRATIVE_DRAFT" for day in outline)


def test_reviewer_guard_rejects_duplicate_place_and_activity():
    base = [{"day_number": 1}, {"day_number": 2}]
    repeated = ModelPlan(days=[ModelDay(
        day_number=number, title=f"Lake idea {number}", note="A gentle illustrative lake visit.",
        attraction="Lake Wakatipu", activities=["Consider the lake with a guide."],
        rest_note="Take a seated break after the visit.", intensity="LOW",
        verification_notes=["Confirm current access details."]) for number in (1, 2)])
    with pytest.raises(ValueError, match="repeated"):
        validate_plan(repeated, base, ["Lake Wakatipu"])
    assert deterministic_findings([day.model_dump() for day in repeated.days], {"days": base})
