import os
from decimal import Decimal

from google import genai
from google.genai import types
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, field_validator

from app.config import settings
from app.skills.contracts import RequirementInput, RequirementOutput
from app.skills.domain import normalize_currency, validate_requirements
from app.skills.destinations import resolve_destination


class GeminiRequirementFields(BaseModel):
    destination: str | None = None
    traveler_count: int | None = None
    duration_days: int | None = None
    budget: float | None = None
    currency: str | None = None
    elevator_required: bool = False

    @field_validator("traveler_count", "duration_days")
    @classmethod
    def positive_count(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("Count must be positive")
        return value

    @field_validator("budget")
    @classmethod
    def positive_budget(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("Budget must be positive")
        return value


def extract_requirements_live(data: RequirementInput) -> tuple[RequirementOutput, dict]:
    """Use one bounded provider call; never substitute deterministic output on failure."""
    if settings.llm_provider == "gemini":
        return _extract_with_gemini(data)
    model = ChatOpenAI(model=settings.model_name, timeout=12, max_retries=0, max_tokens=300,
                       model_kwargs={"response_format": {"type": "json_object"}})
    response = model.invoke([
        SystemMessage(content=(
            "Extract travel requirements as a JSON object with destination, departure_date, "
            "traveler_count, duration_days, budget, currency, elevator_required. "
            "Use null for absent fields. Do not invent a currency or date. "
            "Output JSON only. No supplier facts or prices."
        )),
        HumanMessage(content=f"Request: {data.request}\nExplicit demo date: {data.demo_date or 'not supplied'}"),
    ])
    result = RequirementOutput.model_validate_json(str(response.content))
    if result.currency:
        result.currency = normalize_currency(result.currency)
    if result.departure_date != data.demo_date:
        result.departure_date = data.demo_date
    result.missing_fields = validate_requirements(result)
    usage = response.usage_metadata or {}
    return result, {"input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens")}


def _extract_with_gemini(data: RequirementInput) -> tuple[RequirementOutput, dict]:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"],
                          http_options=types.HttpOptions(timeout=12000,
                                                         retry_options=types.HttpRetryOptions(attempts=1)))
    response = client.models.generate_content(
        model=settings.gemini_requirements_model,
        contents=f"Travel request: {data.request}\nExplicit departure date: {data.demo_date or 'none'}",
        config=types.GenerateContentConfig(
            system_instruction=("Extract only facts stated in the travel request. Return JSON matching the schema. "
                                "Use null for missing values. Do not invent supplier facts, a date, or a currency. "
                                "If the request says NZD or New Zealand dollars, use currency NZD."),
            response_mime_type="application/json", response_schema=GeminiRequirementFields,
            max_output_tokens=1200, thinking_config=types.ThinkingConfig(thinking_level="LOW"),
            temperature=0,
        ),
    )
    fields = GeminiRequirementFields.model_validate_json(response.text or "")
    canonical, scope = resolve_destination(fields.destination or "")
    result = RequirementOutput(destination=canonical, destination_scope=scope,
                               departure_date=data.demo_date, traveler_count=fields.traveler_count,
                               duration_days=fields.duration_days,
                               budget=Decimal(str(fields.budget)) if fields.budget is not None else None,
                               currency=normalize_currency(fields.currency) if fields.currency else None,
                               elevator_required=fields.elevator_required)
    result.missing_fields = validate_requirements(result)
    usage = response.usage_metadata
    return result, {"input_tokens": getattr(usage, "prompt_token_count", None),
                    "output_tokens": getattr(usage, "candidates_token_count", None)}
