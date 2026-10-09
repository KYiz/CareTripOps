from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class RequirementInput(BaseModel):
    request: str = Field(min_length=8)
    demo_date: date | None = None


class RequirementOutput(BaseModel):
    destination: str | None = None
    destination_scope: Literal["SUPPORTED", "OUTSIDE_NZ", "UNKNOWN"] = "UNKNOWN"
    attractions: list[str] = Field(default_factory=list)
    travel_pace: Literal["RELAXED", "STANDARD"] = "STANDARD"
    departure_date: date | None = None
    traveler_count: int | None = Field(default=None, ge=1)
    duration_days: int | None = Field(default=None, ge=1)
    budget: Decimal | None = Field(default=None, gt=0)
    currency: str | None = None
    elevator_required: bool = False
    missing_fields: list[str] = Field(default_factory=list)


class DraftPlanInput(BaseModel):
    destination: str | None = None
    destination_scope: Literal["SUPPORTED", "OUTSIDE_NZ", "UNKNOWN"]
    duration_days: int | None = Field(default=None, ge=1)
    attractions: list[str] = Field(default_factory=list)
    interest_tags: list[str] = Field(default_factory=list)
    travel_pace: Literal["RELAXED", "STANDARD"] = "STANDARD"


class DraftDay(BaseModel):
    day_number: int = Field(ge=1)
    title: str
    note: str
    attraction: str | None = None
    activities: list[str] = Field(default_factory=list)
    rest_note: str = "Leave time to rest between activities."
    intensity: Literal["LOW", "MODERATE"] = "LOW"
    verification_notes: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    status: Literal["ILLUSTRATIVE_DRAFT"] = "ILLUSTRATIVE_DRAFT"


class OfferData(BaseModel):
    product_id: str
    total_amount: Decimal
    currency: Literal["NZD"] = "NZD"
    includes: list[str]
    claims: dict[str, bool | None]
    expires_at: datetime


class EvidenceData(BaseModel):
    claim_type: str
    source: str
    polarity: Literal["SUPPORT", "CONTRADICT", "UNKNOWN"]
    strength: Literal["STRONG", "WEAK"]
    reference: str
    detail: str


class AssessmentData(BaseModel):
    verdict: Literal["PASS", "BLOCK", "REVIEW"]
    reason_code: str
    source_refs: list[str]


class RankingInput(BaseModel):
    budget: Decimal
    currency: Literal["NZD"] = "NZD"
    offers: list[OfferData]
    excluded_ids: list[str] = Field(default_factory=list)


class RankingOutput(BaseModel):
    ordered_product_ids: list[str]


class ApprovalInput(BaseModel):
    case_id: str
    offer_id: str
    offer_version: int = Field(ge=1)
    amount: Decimal = Field(gt=0)
    currency: str
    expires_at: datetime


class BookingInput(BaseModel):
    case_id: str
    approval_id: str
    offer_id: str
    idempotency_key: str


class ReviewInput(BaseModel):
    case_id: str
    order_id: str
    offer_id: str


class ReviewOutput(BaseModel):
    summary: str
    status: Literal["DEMO_COMPLETED"] = "DEMO_COMPLETED"
