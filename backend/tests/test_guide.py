import pytest

from app.guide import guide_answer
from app.guide_text import classify_intent
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


@pytest.mark.parametrize("message, intent", [
    ("能换一家便宜点的酒店吗？", "PACKAGE_CHANGE"),
    ("我有点累了，安排得轻松些吧。", "REVISION"),
    ("下一站是哪里？", "NEXT_ACTIVITY"),
    ("介绍一下这个地方", "ATTRACTION_QUESTION"),
    ("酒店有电梯吗？", "ACCESS_QUESTION"),
    ("Does the hotel have a lift?", "ACCESS_QUESTION"),
    ("Can we switch to a cheaper hotel with a lift?", "PACKAGE_CHANGE"),
    # Keeping the hotel is not a request to change it.
    ("I do not want to change the hotel, just tell me about the lift", "ACCESS_QUESTION"),
    ("I don't need to switch hotels. Is the bathroom accessible?", "ACCESS_QUESTION"),
    ("酒店不用换，就想问问有没有电梯", "ACCESS_QUESTION"),
    ("不换酒店，下一站去哪里？", "NEXT_ACTIVITY"),
    ("Please don't change my booking, I'm tired, can we rest more?", "REVISION"),
])
def test_chinese_messages_are_classified(message, intent):
    assert classify_intent(message) == intent


def test_guide_answers_in_the_requested_language():
    from app.guide_text import language_of

    assert language_of("zh-CN,zh;q=0.9") == "zh" and language_of("en-NZ") == "en" and language_of(None) == "en"
    reply = guide_answer(sample_context(), "下一站是哪里？", "zh")
    assert reply["intent"] == "NEXT_ACTIVITY"
    assert "皇后镇天际缆车" in reply["reply"] and "下一站" in reply["reply"]
    assert "重新核验" in guide_answer(sample_context(), "能换酒店吗", "zh")["reply"]


@pytest.mark.parametrize("note", ["步行大约 20 分钟就能到。", "门票已预订好了。", "费用约 50 纽币。"])
def test_structured_model_plan_rejects_unverified_chinese_claims(note):
    original = sample_context()["days"]
    plan = ModelPlan(days=[
        model_day(1, "轻松的湖边一天", note.ljust(10, "。"), "Lake Wakatipu"),
        model_day(2, "轻松的缆车之旅", "继续之前先留出休息时间。", "Skyline Queenstown"),
    ])
    with pytest.raises(ValueError, match="unverified"):
        validate_plan(plan, original, ["Lake Wakatipu", "Skyline Queenstown"])



def test_place_answers_cite_the_official_page():
    context = {**sample_context(), "place_sources": {"Skyline Queenstown": "https://www.newzealand.com/skyline"}}
    reply = guide_answer(context, "What is next?")
    assert reply["citations"] == [{"kind": "PLACE", "title": "Skyline Queenstown", "url": "https://www.newzealand.com/skyline"}]


def test_access_answers_only_repeat_verified_claims_with_their_evidence():
    stay = {"name": "Lakefront Lodge", "verified_claims": ["lift_serves_all_guest_floors", "step_free_entry"],
            "evidence": [{"claim": "step_free_entry", "reference": "AUD-1", "detail": "Ramped entrance.",
                          "url": "https://supplier.example/evidence/AUD-1"}]}
    reply = guide_answer({**sample_context(), "stay": stay}, "Is there a lift and no stairs?")
    assert reply["intent"] == "ACCESS_QUESTION"
    assert "a lift to every guest floor, step-free entry" in reply["reply"]
    assert reply["citations"] == [{"kind": "EVIDENCE", "title": "AUD-1: Ramped entrance.",
                                   "url": "https://supplier.example/evidence/AUD-1"}]
    assert "无台阶入口" in guide_answer({**sample_context(), "stay": stay}, "有电梯吗？", "zh")["reply"]
    none = guide_answer({**sample_context(), "stay": None}, "Is it wheelchair accessible?")
    assert none["citations"] == [] and "No stay has been chosen" in none["reply"]
    no_need = guide_answer({**sample_context(), "stay": {**stay, "verified_claims": ["no_access_need"]}}, "Is there a lift?")
    assert "none were checked" in no_need["reply"]
