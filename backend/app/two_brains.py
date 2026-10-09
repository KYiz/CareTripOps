"""Bounded Gemini planner/reviewer loop for illustrative itinerary drafts."""

import asyncio
import json
import os
import re
from typing import Literal

from pydantic import BaseModel, model_validator
from sqlalchemy import select

from app.config import settings
from app.db import Case, SessionLocal, add_event
from app.skills.destinations import ATTRACTION_CATALOG


class ModelDay(BaseModel):
    day_number: int
    title: str
    note: str
    attraction: str | None = None
    activities: list[str]
    rest_note: str
    intensity: Literal["LOW", "MODERATE"]
    verification_notes: list[str]

    @model_validator(mode="after")
    def validate_content(self):
        if not 1 <= self.day_number <= 14 or not 3 <= len(self.title) <= 120:
            raise ValueError("Invalid itinerary day or title")
        if not 10 <= len(self.note) <= 240 or not 8 <= len(self.rest_note) <= 160:
            raise ValueError("Itinerary note or rest advice is incomplete")
        if not 1 <= len(self.activities) <= 3 or not 1 <= len(self.verification_notes) <= 3:
            raise ValueError("Itinerary activity or verification count is invalid")
        return self


class ModelPlan(BaseModel):
    days: list[ModelDay]

    @model_validator(mode="after")
    def validate_days(self):
        if not 1 <= len(self.days) <= 14:
            raise ValueError("An itinerary needs one to fourteen days")
        return self


class ReviewFeedback(BaseModel):
    concerns: list[str]
    recommendation: str
    requires_revision: bool = False

    @model_validator(mode="after")
    def validate_feedback(self):
        if len(self.concerns) > 5 or not 10 <= len(self.recommendation) <= 300:
            raise ValueError("Reviewer feedback is invalid")
        return self


def planning_enabled() -> bool:
    return (settings.model_mode == "api" and settings.llm_provider == "gemini"
            and os.getenv("GEMINI_PLANNING_ENABLED", "false").lower() == "true")


def validate_plan(plan: ModelPlan, original: list[dict], attractions: list[str]) -> list[dict]:
    if len(plan.days) != len(original):
        raise ValueError("Model plan changed the number of travel days")
    allowed = set(attractions)
    seen_places: set[str] = set()
    seen_activities: set[str] = set()
    known_places = {name for places in ATTRACTION_CATALOG.values() for name in places}
    for expected, day in zip(original, plan.days):
        if day.day_number != expected["day_number"] or (day.attraction and day.attraction not in allowed):
            raise ValueError("Model plan used a day or attraction outside the case")
        if day.attraction and day.attraction in seen_places:
            raise ValueError("Model plan repeated an attraction")
        if day.attraction:
            seen_places.add(day.attraction)
        if any(not activity.strip() or activity.casefold() in seen_activities for activity in day.activities):
            raise ValueError("Model plan contains an empty or repeated activity")
        seen_activities.update(activity.casefold() for activity in day.activities)
        content = " ".join([day.title, day.note, day.rest_note, *day.activities, *day.verification_notes])
        if any(name in content for name in known_places - allowed):
            raise ValueError("Model plan mentioned an attraction outside the case")
        if re.search(r"(?:NZD|\$\s*\d|\b\d+\s*(?:minutes?|hours?|km)\b|\b(?:booked|reserved)\b)",
                     content, re.IGNORECASE):
            raise ValueError("Model plan asserted an unverified price, duration, distance, or booking")
    catalog = {name: item for places in ATTRACTION_CATALOG.values() for name, item in places.items()}
    return [{**day.model_dump(), "status": "ILLUSTRATIVE_DRAFT",
             "source_urls": [catalog[day.attraction]["source_url"]] if day.attraction in catalog else []}
            for day in plan.days]


def deterministic_findings(days: list[dict], context: dict) -> list[str]:
    findings = []
    if len(days) != len(context["days"]):
        findings.append("Day count differs from the confirmed requirement")
    places = [day.get("attraction") for day in days if day.get("attraction")]
    if len(places) != len(set(places)):
        findings.append("An attraction is repeated")
    if any(not day.get("rest_note") for day in days):
        findings.append("A rest recommendation is missing")
    if any(len(day.get("activities", [])) > 3 for day in days):
        findings.append("A day contains too many activities")
    return findings


def _reserve_call(case_id: str, role: str, model: str) -> None:
    with SessionLocal.begin() as session:
        case = session.get(Case, case_id, with_for_update=True)
        if case.llm_calls >= settings.max_llm_calls:
            raise ValueError("Model call limit reached for this case")
        case.llm_calls += 1
        add_event(session, case_id, role, "MODEL_CALL_STARTED", case.status,
                  {"role": role, "model": model, "call_number": case.llm_calls})


async def _call(client, case_id: str, role: str, model: str, prompt: str, schema: type[BaseModel]):
    from google.genai import types

    _reserve_call(case_id, role, model)
    try:
        response = await asyncio.wait_for(client.aio.models.generate_content(
            model=model, contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json",
                                               response_schema=schema,
                                               max_output_tokens=2500 if schema is ModelPlan else 1000,
                                               thinking_config=types.ThinkingConfig(thinking_level="LOW"),
                                               temperature=0.2)), timeout=30)
        result = schema.model_validate_json(response.text or "")
    except Exception as exc:
        with SessionLocal.begin() as session:
            case = session.get(Case, case_id)
            add_event(session, case_id, role, "MODEL_CALL_FAILED", case.status,
                      {"role": role, "model": model, "error_type": type(exc).__name__})
        raise
    usage = response.usage_metadata
    with SessionLocal.begin() as session:
        case = session.get(Case, case_id)
        add_event(session, case_id, role, "MODEL_CALL_COMPLETED", case.status,
                  {"role": role, "model": model,
                   "input_tokens": getattr(usage, "prompt_token_count", None),
                   "output_tokens": getattr(usage, "candidates_token_count", None)})
    return result


async def review_itinerary(case_id: str, request: str, context: dict) -> tuple[list[dict], dict]:
    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError("Gemini planning is enabled but no API key is configured")
    with SessionLocal() as session:
        case = session.get(Case, case_id)
        if not case or case.llm_calls + 2 > settings.max_llm_calls:
            raise ValueError("Planner and reviewer calls are not available within this case limit")
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"],
                          http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1)))
    planner_model = os.getenv("GEMINI_PLANNER_MODEL", "gemini-3.8-flash")
    reviewer_model = os.getenv("GEMINI_REVIEWER_MODEL", "gemini-3.8-flash")
    base = {"destination": context["destination"], "pace": context["travel_pace"],
            "traveler_count": context["traveler_count"], "elevator_required": context["elevator_required"],
            "budget": context.get("budget"), "currency": context.get("currency"),
            "allowed_attractions": context["attractions"], "current_days": context["days"],
            "place_sources": context.get("place_sources", {}),
            "traveler_request": request}
    initial = await _call(client, case_id, "Travel Planner", planner_model,
                          "Create distinct, personalized illustrative days from the stated interests and supplied places. "
                          "Use exactly one or two ordered gentle activities per day, exactly one verification note, "
                          "a specific rest suggestion, intensity LOW or MODERATE, and one main place per day at most. "
                          "Keep the day count and order. Do not repeat places or activities. "
                          "The place source URLs only establish the place name and theme; they do not verify current access. "
                          "No prices, travel times, opening hours, inventory, facility or booking claims. "
                          + json.dumps(base), ModelPlan)
    initial_days = validate_plan(initial, context["days"], context["attractions"])
    feedback = await _call(client, case_id, "Travel Reviewer", reviewer_model,
                           "Independently review the draft for the traveler's interests, budget awareness, number of days, "
                           "duplicate places or activities, too many activities, rest, mobility needs, and unsupported "
                           "time or transport assumptions. Set requires_revision only for concrete concerns. "
                           "Do not assert unverified facts. "
                           + json.dumps({**base, "planner_initial": initial_days}), ReviewFeedback)
    findings = deterministic_findings(initial_days, context)
    if findings:
        feedback.concerns.extend(findings)
        feedback.requires_revision = True
    revised_days = initial_days
    revision_applied = False
    if feedback.requires_revision or feedback.concerns:
        revised = await _call(client, case_id, "Travel Planner", planner_model,
                              "Revise the draft once using the independent review. Resolve every concrete concern. "
                              "Keep the same day count and allowed places, exactly one or two activities and one "
                              "verification note per day, with no duplicates or unverified logistics. "
                              + json.dumps({**base, "planner_initial": initial_days,
                                            "reviewer_feedback": feedback.model_dump()}), ModelPlan)
        revised_days = validate_plan(revised, context["days"], context["attractions"])
        revision_applied = True
        if deterministic_findings(revised_days, context):
            raise ValueError("Revised plan still fails deterministic review")
    return revised_days, {"mode": "GEMINI_TWO_BRAINS", "planner_model": planner_model,
                          "reviewer_model": reviewer_model, "planner_initial": initial_days,
                          "reviewer_feedback": feedback.model_dump(), "planner_revised": revised_days,
                          "revision_applied": revision_applied}
