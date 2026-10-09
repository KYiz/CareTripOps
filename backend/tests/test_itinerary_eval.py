import importlib.util
from pathlib import Path

from app.two_brains import ModelDay, ModelPlan


spec = importlib.util.spec_from_file_location("itinerary_eval", Path(__file__).parents[1] / "evals" / "itinerary_eval.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_ten_cases_have_explicit_new_zealand_scope():
    assert len(module.CASES) == 10
    assert all(destination and attractions and request for destination, attractions, request in module.CASES)


def test_scoring_detects_unverified_booking_and_missing_rest():
    plan = ModelPlan(days=[
        ModelDay(day_number=1, title="Lake day", note="We booked a room for you.", attraction="Lake Wakatipu",
                 activities=["Consider the lake."], rest_note="Find a seat for a rest.", intensity="LOW",
                 verification_notes=["Confirm access."]),
        ModelDay(day_number=2, title="Gondola day", note="The ride takes 10 minutes.", attraction="Skyline Queenstown",
                 activities=["Consider the gondola."], rest_note="Find a seat for a rest.", intensity="LOW",
                 verification_notes=["Confirm access."]),
        ModelDay(day_number=3, title="Open day", note="Choose activities as you like.", attraction=None,
                 activities=["Keep an open day."], rest_note="Find a seat for a rest.", intensity="LOW",
                 verification_notes=["Confirm plans."]),
    ])
    result = module.score_plan(plan, ["Lake Wakatipu", "Skyline Queenstown"])
    assert result["score"] == 2
    assert result["no_unverified_claims"] is False
