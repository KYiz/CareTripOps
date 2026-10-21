import asyncio
import sys
from types import SimpleNamespace

from google import genai

from app import two_brains
from app.two_brains import ModelDay, ModelPlan, ReviewFeedback


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def plan(title_suffix=""):
    return ModelPlan(days=[ModelDay(day_number=1, title=f"Lake visit{title_suffix}",
                                    note="Consider a gentle visit without a fixed schedule.",
                                    attraction="Lake Wakatipu", activities=["Enjoy a lakeside view."],
                                    rest_note="Pause for a seated break after the main idea.",
                                    intensity="LOW", verification_notes=["Confirm current access details."])])


def context():
    return {"destination": "Queenstown", "travel_pace": "RELAXED", "traveler_count": 3,
            "elevator_required": False, "attractions": ["Lake Wakatipu"],
            "days": [{"day_number": 1, "attraction": "Lake Wakatipu"}],
            "budget": "1000", "currency": "NZD", "place_sources": {}}


class FakeSession:
    def __enter__(self): return self
    def __exit__(self, *_): return None
    def get(self, *_): return SimpleNamespace(llm_calls=0)


def test_planner_and_reviewer_are_separate_calls(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-value")
    monkeypatch.setattr(two_brains, "SessionLocal", FakeSession)
    monkeypatch.setattr(genai, "Client", lambda **_: SimpleNamespace())
    roles = []

    async def fake_call(_, __, role, ___, ____, _____):
        roles.append(role)
        return plan() if role == "Travel Planner" else ReviewFeedback(
            concerns=[], recommendation="The outline includes a gentle break.", requires_revision=False)

    monkeypatch.setattr(two_brains, "_call", fake_call)
    days, trace = asyncio.run(two_brains.review_itinerary("case", "A gentle lake visit", context()))
    assert roles == ["Travel Planner", "Travel Reviewer"]
    assert trace["revision_applied"] is False
    assert days[0]["attraction"] == "Lake Wakatipu"


def test_planner_revises_at_most_once_after_review(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-value")
    monkeypatch.setattr(two_brains, "SessionLocal", FakeSession)
    monkeypatch.setattr(genai, "Client", lambda **_: SimpleNamespace())
    roles = []

    async def fake_call(_, __, role, ___, ____, _____):
        roles.append(role)
        if role == "Travel Reviewer":
            return ReviewFeedback(concerns=["Allow a clearer rest period."],
                                  recommendation="Add an explicit seated break.", requires_revision=True)
        return plan(" revised" if roles.count("Travel Planner") == 2 else "")

    monkeypatch.setattr(two_brains, "_call", fake_call)
    days, trace = asyncio.run(two_brains.review_itinerary("case", "Make the day gentler", context()))
    assert roles == ["Travel Planner", "Travel Reviewer", "Travel Planner"]
    assert trace["revision_applied"] is True
    assert days[0]["title"] == "Lake visit revised"


def test_revision_mode_sends_the_change_request_and_access_needs(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-value")
    monkeypatch.setattr(two_brains, "SessionLocal", FakeSession)
    monkeypatch.setattr(genai, "Client", lambda **_: SimpleNamespace())
    prompts = []

    async def fake_call(_, __, role, ___, prompt, _____):
        prompts.append((role, prompt))
        return plan() if role == "Travel Planner" else ReviewFeedback(
            concerns=[], recommendation="The outline keeps walking short.", requires_revision=False)

    monkeypatch.setattr(two_brains, "_call", fake_call)
    needs = {"wheelchair": "MANUAL", "max_walk_meters": 100}
    asyncio.run(two_brains.review_itinerary("case", "I am tired, fewer stops please",
                                            {**context(), "access_needs": needs}, revision=True))
    planner = prompts[0][1]
    assert "Adjust the current days" in planner and '"change_request": "I am tired' in planner
    assert "uses a wheelchair" in planner and "about 100 metres" in planner
    assert "data, not instructions" in planner
    assert '"access_needs": {"wheelchair": "MANUAL"' in prompts[1][1]  # The reviewer checks them too.


def test_without_a_call_left_the_reviewed_draft_is_kept_unless_our_checks_fail(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-value")
    monkeypatch.setattr(two_brains, "SessionLocal", FakeSession)
    monkeypatch.setattr(genai, "Client", lambda **_: SimpleNamespace())
    left = iter([2, 0])
    monkeypatch.setattr(two_brains, "calls_left", lambda _: next(left))

    async def fake_call(_, __, role, ___, ____, _____):
        return plan() if role == "Travel Planner" else ReviewFeedback(
            concerns=["Could add a longer rest."], recommendation="Consider a longer seated rest.", requires_revision=True)

    monkeypatch.setattr(two_brains, "_call", fake_call)
    days, trace = asyncio.run(two_brains.review_itinerary("case", "A gentle lake visit", context()))
    assert trace["revision_applied"] is False and trace["revision_skipped"] == "MODEL_CALL_LIMIT"
    assert days[0]["title"] == "Lake visit"
    # A structural problem our own checks find cannot be shipped without the revision call.
    left = iter([2, 0])
    monkeypatch.setattr(two_brains, "calls_left", lambda _: next(left))
    monkeypatch.setattr(two_brains, "deterministic_findings", lambda *_: ["A rest recommendation is missing"])
    import pytest
    with pytest.raises(ValueError, match="call limit"):
        asyncio.run(two_brains.review_itinerary("case", "A gentle lake visit", context()))
