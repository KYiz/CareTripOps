import pytest

from app.guide import classify_intent, guide_answer
from app.two_brains import ModelDay, ModelPlan, validate_plan


def sample_context():
    return {
        "destination": "Queenstown", "travel_pace": "RELAXED",
        "selected_attraction": "Lake Wakatipu",
        "days": [
            {"day_number": 1, "title": "Lake Wakatipu", "note": "Illustrative lake day", "attraction": "Lake Wakatipu"},
            {"day_number": 2, "title": "Skyline Queenstown", "note": "Illustrative gondola day", "attraction": "Skyline Queenstown"},
        ],
    }


def model_day(day_number, title, note, attraction):
    return ModelDay(day_number=day_number, title=title, note=note, attraction=attraction,
                    activities=[f"Consider {attraction or 'a flexible local idea'} with a guide."],
                    rest_note="Leave a seated break after the main idea.", intensity="LOW",
                    verification_notes=["Confirm current visitor details."])


def test_guide_uses_only_case_outline_for_next_stop():
    reply = guide_answer(sample_context(), "What is next?")
    assert reply["intent"] == "NEXT_ACTIVITY"
    assert "Skyline Queenstown" in reply["reply"]
    assert reply["model_mode"] == "deterministic"


def test_tired_request_routes_to_revision_without_claiming_booking():
    assert classify_intent("I am tired. Can we change the plan?") == "REVISION"
    reply = guide_answer(sample_context(), "I am tired")
    assert reply["intent"] == "REVISION"
    assert "will not change a verified offer or booking" in reply["reply"]


def test_package_change_requires_new_verification():
    reply = guide_answer(sample_context(), "Can I change the hotel and price?")
    assert reply["intent"] == "PACKAGE_CHANGE"
    assert "fresh verification" in reply["reply"]


def test_structured_model_plan_rejects_unlisted_attraction():
    original = sample_context()["days"]
    plan = ModelPlan(days=[
        model_day(1, "A relaxed lake visit", "Leave time for a gentle rest.", "Lake Wakatipu"),
        model_day(2, "A different place", "Leave time for a gentle rest.", "Milford Sound"),
    ])
    with pytest.raises(ValueError, match="outside the case"):
        validate_plan(plan, original, ["Lake Wakatipu", "Skyline Queenstown"])


def test_structured_model_plan_keeps_day_count_and_draft_status():
    original = sample_context()["days"]
    plan = ModelPlan(days=[
        model_day(1, "Gentle lake visit", "Leave time for a gentle rest.", "Lake Wakatipu"),
        model_day(2, "Easy gondola idea", "Allow a break before continuing.", "Skyline Queenstown"),
    ])
    result = validate_plan(plan, original, ["Lake Wakatipu", "Skyline Queenstown"])
    assert len(result) == 2
    assert all(day["status"] == "ILLUSTRATIVE_DRAFT" for day in result)


def test_structured_model_plan_rejects_unverified_transport_time():
    original = sample_context()["days"]
    plan = ModelPlan(days=[
        model_day(1, "Gentle lake visit", "The journey takes 20 minutes.", "Lake Wakatipu"),
        model_day(2, "Easy gondola idea", "Allow a break before continuing.", "Skyline Queenstown"),
    ])
    with pytest.raises(ValueError, match="unverified"):
        validate_plan(plan, original, ["Lake Wakatipu", "Skyline Queenstown"])
