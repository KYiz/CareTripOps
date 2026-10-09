"""Opt-in, ten-case Gemini planner/reviewer evaluation; never runs on import."""

import argparse
import asyncio
import json
import os
import re
from pathlib import Path

from google import genai
from google.genai import types

from app.two_brains import ModelPlan, ReviewFeedback


CASES = [
    ("Auckland", ["Auckland Harbour", "Sky Tower"], "A gentle three-day trip with regular breaks."),
    ("Queenstown", ["Lake Wakatipu", "Skyline Queenstown"], "Three days with lake views and a slow pace."),
    ("Rotorua", ["Lake Rotorua", "Wai-O-Tapu"], "A relaxed three-day geothermal and lake break."),
    ("Wellington", ["Wellington Harbour"], "Three flexible days with rest after each outing."),
    ("Christchurch", ["Christchurch Botanic Gardens"], "Three days focused on gardens and easy walks."),
    ("Taupō", ["Lake Taupō"], "Three days by the lake without a packed schedule."),
    ("Auckland", ["Auckland Harbour"], "Three travelers want a calm trip and time to sit down."),
    ("Queenstown", ["Skyline Queenstown"], "A family trip with one main activity per day."),
    ("Rotorua", ["Wai-O-Tapu"], "A traveler gets tired easily and needs longer breaks."),
    ("Christchurch", ["Christchurch Botanic Gardens"], "An unhurried visit with a flexible final day."),
]


def score_plan(plan: ModelPlan, attractions: list[str], expected_days: int = 3) -> dict:
    days = plan.days
    correct_days = len(days) == expected_days and [d.day_number for d in days] == list(range(1, expected_days + 1))
    known_places = all(d.attraction is None or d.attraction in attractions for d in days)
    rest = any(re.search(r"\b(rest|break|slow|gentle|flexible)\b", d.note, re.I) for d in days)
    unsupported = any(re.search(r"(?:NZD|\$\s*\d|\b\d+\s*(?:minutes?|hours?|km)\b|\b(?:booked|reserved)\b)",
                                f"{d.title} {d.note}", re.I) for d in days)
    return {"score": int(correct_days) + int(known_places) + int(rest) + int(not unsupported),
            "correct_days": correct_days, "known_places": known_places,
            "rest_or_flexibility": rest, "no_unverified_claims": not unsupported}


async def structured_call(client, model: str, prompt: str, schema):
    response = await asyncio.wait_for(client.aio.models.generate_content(
        model=model, contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=schema,
                                           max_output_tokens=500, temperature=0.2)), timeout=18)
    result = schema.model_validate_json(response.text or "")
    usage = response.usage_metadata
    return result, {"input_tokens": getattr(usage, "prompt_token_count", None),
                    "output_tokens": getattr(usage, "candidates_token_count", None)}


async def run(max_cases: int) -> list[dict]:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is required for a live evaluation")
    client = genai.Client(api_key=key,
                          http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1)))
    planner = os.getenv("GEMINI_PLANNER_MODEL", "gemini-flash-latest")
    reviewer = os.getenv("GEMINI_REVIEWER_MODEL", "gemini-flash-latest")
    results = []
    for index, (destination, attractions, request) in enumerate(CASES[:max_cases], start=1):
        context = {"destination": destination, "allowed_attractions": attractions, "request": request,
                   "day_count": 3, "scope": "illustrative only"}
        item = {"case": index, "destination": destination, "request": request,
                "planner_model": planner, "reviewer_model": reviewer}
        try:
            initial, usage1 = await structured_call(client, planner,
                "Draft three gentle days using only these places. Never claim prices or travel times. " + json.dumps(context), ModelPlan)
            feedback, usage2 = await structured_call(client, reviewer,
                "Review the draft for pace, rest and unsupported claims. " + json.dumps({**context, "draft": initial.model_dump()}), ReviewFeedback)
            revised, usage3 = await structured_call(client, planner,
                "Revise the draft from this review while keeping the same three days and allowed places. "
                + json.dumps({**context, "draft": initial.model_dump(), "feedback": feedback.model_dump()}), ModelPlan)
            item.update({"before": score_plan(initial, attractions), "after": score_plan(revised, attractions),
                         "reviewer_feedback": feedback.model_dump(), "initial": initial.model_dump(),
                         "revised": revised.model_dump(), "provider_usage": [usage1, usage2, usage3]})
        except Exception as exc:
            item.update({"error_type": type(exc).__name__, "before": None, "after": None})
        results.append(item)
    return results


def main():
    parser = argparse.ArgumentParser(description="Run real Gemini itinerary evaluation with explicit opt-in.")
    parser.add_argument("--confirm-live", action="store_true", help="Allow model calls that consume shared quota")
    parser.add_argument("--max-cases", type=int, default=10, choices=range(1, 11))
    parser.add_argument("--output", type=Path, default=Path("evals/itinerary_eval_results.json"))
    args = parser.parse_args()
    if not args.confirm_live:
        parser.error("Pass --confirm-live to run provider calls")
    results = asyncio.run(run(args.max_cases))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    passed = sum(item.get("after", {}).get("score", 0) >= item.get("before", {}).get("score", 0)
                 for item in results if item.get("after") and item.get("before"))
    print(f"Evaluated {len(results)} cases; {passed} non-regressing revisions. Results: {args.output}")


if __name__ == "__main__":
    main()
