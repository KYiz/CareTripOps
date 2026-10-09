import re
import unicodedata
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.skills.contracts import (
    AssessmentData, DraftDay, DraftPlanInput, EvidenceData, OfferData, RankingInput, RankingOutput,
    RequirementInput, RequirementOutput, ReviewInput, ReviewOutput,
)
from app.skills.destinations import ATTRACTION_CATALOG, ATTRACTIONS, resolve_attractions, resolve_destination


REQUIRED_FIELDS = ("destination", "departure_date", "traveler_count", "duration_days", "budget", "currency")


def normalize_currency(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().upper()
    return normalized.translate({ord(char): None for char in "\u200b\u200c\u200d\ufeff"})


def infer_interest_tags(request: str) -> list[str]:
    text = request.casefold()
    patterns = {
        "lake": r"lake|湖|湖景", "gondola": r"gondola|cable car|缆车|纜車",
        "hot-springs": r"spa|hot spring|hot pool|温泉|溫泉|泡汤|泡湯",
        "culture": r"culture|museum|history|文化|博物馆|博物館|历史|歷史",
        "city": r"city|urban|城市|市区|市區", "nature": r"nature|natural|自然|瀑布|waterfall",
        "scenery": r"scenery|scenic|views?|风景|風景|景色",
        "geothermal": r"geothermal|地热|地熱",
    }
    return [tag for tag, pattern in patterns.items() if re.search(pattern, text)]


def extract_requirements(data: RequirementInput) -> RequirementOutput:
    text = unicodedata.normalize("NFKC", data.request).lower().replace("\u200b", "").replace("\u200c", "").replace("\u200d", "")
    destination, scope = resolve_destination(data.request)
    for word, number in {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
                         "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10"}.items():
        text = re.sub(rf"\b{word}\b", number, text)
    travelers = re.search(r"\b(\d+)\s*(?:travelers?|people|guests?)\b", text)
    days = re.search(r"\b(\d+)[\s-]*days?\b", text)
    budget = re.search(r"(?:nzd\s*\$?\s*|\$\s*|纽币\s*|紐幣\s*|新西兰元\s*|紐西蘭元\s*)([\d,]+(?:\.\d{1,2})?)", text)
    chinese_numbers = {"一": 1, "二": 2, "两": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    companion_match = re.search(r"(?:和|跟|与)([一二两兩三四五六七八九十\d]+)(?:个|位)?(?:朋友|同伴|家人)", text)
    chinese_travelers = re.search(r"([一二两兩三四五六七八九十\d]+)(?:个|位)?人", text)
    chinese_days = re.search(r"([一二两兩三四五六七八九十\d]+)天", text)
    chinese_budget = re.search(r"(?:预算|預算)(每人)?\s*(?:新西兰元|紐西蘭元|纽币|紐幣|nzd)?\s*([\d,]+)(?:元)?", text)
    def number(value: str) -> int:
        return int(value) if value.isdigit() else chinese_numbers[value]
    count = int(travelers.group(1)) if travelers else (1 + number(companion_match.group(1)) if companion_match else
            number(chinese_travelers.group(1)) if chinese_travelers else None)
    duration = int(days.group(1)) if days else number(chinese_days.group(1)) if chinese_days else None
    amount = budget.group(1) if budget else chinese_budget.group(2) if chinese_budget else None
    total_budget = Decimal(amount.replace(",", "")) if amount else None
    if chinese_budget and chinese_budget.group(1):
        total_budget = total_budget * count if count else None
    result = RequirementOutput(
        destination=destination, destination_scope=scope,
        attractions=resolve_attractions(data.request, destination),
        travel_pace="RELAXED" if re.search(r"not too tiring|relaxed|easy pace|不想太累|轻松|輕鬆|慢节奏|慢節奏", text) else "STANDARD",
        departure_date=data.demo_date,
        traveler_count=count, duration_days=duration,
        budget=total_budget,
        currency="NZD" if re.search(r"nzd|新西兰元|紐西蘭元|纽币|紐幣", text) else None,
        elevator_required=bool(re.search(r"elevator|lift|step.free|accessible", text)),
    )
    result.missing_fields = validate_requirements(result)
    return result


def validate_requirements(data: RequirementOutput) -> list[str]:
    missing = [field for field in REQUIRED_FIELDS if getattr(data, field) is None]
    if data.destination and resolve_destination(data.destination)[1] != "SUPPORTED" and "destination" not in missing:
        missing.append("destination")
    if data.currency and data.currency != "NZD":
        missing.append("currency")
    return missing


def build_draft_itinerary(data: DraftPlanInput) -> list[DraftDay]:
    """Build a distinct, clearly illustrative outline from the local place catalog."""
    if data.destination_scope != "SUPPORTED" or not data.destination or not data.duration_days:
        return []
    days: list[DraftDay] = []
    catalog = ATTRACTION_CATALOG.get(data.destination, {})
    interests = set(data.interest_tags)
    ranked = sorted(catalog, key=lambda name: (-len(interests.intersection(catalog[name]["themes"])),
                                               list(catalog).index(name)))
    names = list(dict.fromkeys([*data.attractions, *ranked, *ATTRACTIONS.get(data.destination, {})]))
    rest_note = ("Keep a generous seated break and leave the afternoon flexible." if data.travel_pace == "RELAXED"
                 else "Leave a break between activities and adjust the pace as needed.")
    for day_number in range(1, min(data.duration_days, 14) + 1):
        attraction = names[day_number - 1] if day_number <= len(names) else None
        place = catalog.get(attraction or "", {})
        title = (f"Explore {attraction}" if attraction else
                 ["A flexible local day", "A gentle discovery day", "An open day at your pace"][(day_number - len(names) - 1) % 3])
        note = (f"{attraction} is a possible stop. Confirm access, availability and travel details before visiting."
                if attraction else "Choose a confirmed local activity with your advisor; no visit is assumed.")
        activities = ([f"Consider {attraction} after checking current visitor information."] if attraction else
                      ["Choose an accessible local activity after confirming the details."])
        days.append(DraftDay(day_number=day_number, title=title, note=note, attraction=attraction,
                             activities=activities, rest_note=rest_note, intensity="LOW" if data.travel_pace == "RELAXED" else "MODERATE",
                             verification_notes=["Opening, access, transport and availability require confirmation."],
                             source_urls=[place["source_url"]] if place.get("source_url") else []))
    return days


def search_suppliers(requirements: RequirementOutput) -> list[OfferData]:
    if validate_requirements(requirements):
        raise ValueError("Requirements must be complete before supplier discovery")
    if (requirements.destination != "Auckland" or requirements.currency != "NZD"
            or requirements.traveler_count != 3 or requirements.duration_days != 3):
        return []
    expiry = datetime.now(timezone.utc) + timedelta(days=7)
    includes = ["Three-day accommodation", "Local transport", "Sample activities"]
    return [
        OfferData(product_id="PACKAGE_A", total_amount=Decimal("820.00"), includes=includes,
                  claims={"lift_serves_all_guest_floors": False}, expires_at=expiry),
        OfferData(product_id="PACKAGE_C", total_amount=Decimal("880.00"), includes=includes,
                  claims={"lift_serves_all_guest_floors": None}, expires_at=expiry),
        OfferData(product_id="PACKAGE_B", total_amount=Decimal("920.00"), includes=includes,
                  claims={"lift_serves_all_guest_floors": True}, expires_at=expiry),
    ]


def compare_offers(data: RankingInput) -> RankingOutput:
    eligible = [o for o in data.offers if o.currency == data.currency and o.total_amount <= data.budget
                and o.product_id not in data.excluded_ids]
    eligible.sort(key=lambda item: (item.total_amount, item.product_id))
    return RankingOutput(ordered_product_ids=[o.product_id for o in eligible])


def synthetic_evidence(product_id: str) -> list[EvidenceData]:
    facts = {
        "PACKAGE_A": [
            ("official_amenity", "SUPPORT", "WEAK", "CAT-A-1", "A lift is listed; floor coverage is unspecified."),
            ("guest_review", "CONTRADICT", "STRONG", "REV-A-2", "A half-flight of stairs remains."),
            ("support_ticket", "CONTRADICT", "STRONG", "TKT-A-3", "Guest reports stairs to accommodation."),
        ],
        "PACKAGE_C": [("official_amenity", "UNKNOWN", "WEAK", "CAT-C-1", "Guest-floor lift coverage is unlisted.")],
        "PACKAGE_B": [("official_amenity", "SUPPORT", "STRONG", "CAT-B-1", "Lift serves all guest floors in the synthetic catalog.")],
    }
    return [EvidenceData(claim_type="lift_serves_all_guest_floors", source=source,
                         polarity=polarity, strength=strength, reference=reference, detail=detail)
            for source, polarity, strength, reference, detail in facts[product_id]]


def verify_evidence(product_id: str, elevator_required: bool) -> tuple[list[EvidenceData], AssessmentData]:
    sources = synthetic_evidence(product_id)
    refs = [item.reference for item in sources]
    if not elevator_required:
        result = AssessmentData(verdict="PASS", reason_code="NO_ACCESSIBILITY_CONSTRAINT", source_refs=refs)
    elif any(item.polarity == "CONTRADICT" for item in sources):
        result = AssessmentData(verdict="BLOCK", reason_code="ACCESSIBILITY_CONFLICT", source_refs=refs)
    elif any(item.polarity == "SUPPORT" and item.strength == "STRONG" for item in sources):
        result = AssessmentData(verdict="PASS", reason_code="SYNTHETIC_SOURCE_SUPPORT", source_refs=refs)
    else:
        result = AssessmentData(verdict="REVIEW", reason_code="INSUFFICIENT_FLOOR_COVERAGE", source_refs=refs)
    return sources, result


def rerank_offers(data: RankingInput, verdicts: dict[str, str]) -> RankingOutput:
    ordered = compare_offers(data).ordered_product_ids
    return RankingOutput(ordered_product_ids=[item for item in ordered if verdicts.get(item) not in {"BLOCK", "REVIEW"}])


def generate_review(data: ReviewInput) -> ReviewOutput:
    return ReviewOutput(summary=f"Simulated order {data.order_id} for offer {data.offer_id} was committed for case {data.case_id}.")
