import re
import unicodedata
from datetime import date
from decimal import Decimal

from app.skills.contracts import (
    AssessmentData, DraftDay, DraftPlanInput, EvidenceData, OfferData, RankedOffer, RankingInput, RankingOutput,
    RequirementInput, RequirementOutput, ReviewInput, ReviewOutput,
)
from app.skills.destinations import ATTRACTION_CATALOG, ATTRACTIONS, local_name, resolve_attractions, resolve_destination


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
    # Amounts must start with a digit: NFKC turns a full-width "，" after 纽币 into "," otherwise.
    budget = re.search(r"(?:nzd\s*\$?\s*|\$\s*|纽币\s*|紐幣\s*|新西兰元\s*|紐西蘭元\s*)(\d[\d,]*(?:\.\d{1,2})?)", text)
    chinese_numbers = {"一": 1, "二": 2, "两": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    companion_match = re.search(r"(?:和|跟|与)([一二两兩三四五六七八九十\d]+)(?:个|位)?(?:朋友|同伴|家人)", text)
    chinese_travelers = re.search(r"([一二两兩三四五六七八九十\d]+)(?:个|位)?人", text)
    chinese_days = re.search(r"([一二两兩三四五六七八九十\d]+)天", text)
    chinese_budget = re.search(r"(?:预算|預算)(每人)?\s*(?:新西兰元|紐西蘭元|纽币|紐幣|nzd)?\s*(\d[\d,]*)(?:元)?", text)
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
        elevator_required=bool(re.search(r"elevator|lift|step.free|accessible|电梯|電梯|无障碍|無障礙|轮椅|輪椅", text)),
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


DRAFT_TEXT = {
    "en": {
        "rest_relaxed": "Keep a generous seated break and leave the afternoon flexible.",
        "rest_standard": "Leave a break between activities and adjust the pace as needed.",
        "title": "Explore {place}", "open_titles": ["A flexible local day", "A gentle discovery day", "An open day at your pace"],
        "note": "{place} is a possible stop. Confirm access, availability and travel details before visiting.",
        "open_note": "Choose a confirmed local activity with your advisor; no visit is assumed.",
        "activity": "Consider {place} after checking current visitor information.",
        "open_activity": "Choose an accessible local activity after confirming the details.",
        "verify": "Opening, access, transport and availability require confirmation.",
        "verify_access": "Check step-free access, an accessible toilet and the distance from the drop-off point.",
    },
    "zh": {
        "rest_relaxed": "安排充足的坐下休息时间，下午保持灵活。",
        "rest_standard": "活动之间留出休息时间，按需要调整节奏。",
        "title": "游览{place}", "open_titles": ["自由安排的一天", "轻松探索的一天", "按你节奏的一天"],
        "note": "{place}是可选的一站。出发前请确认无障碍设施、开放情况和交通。",
        "open_note": "请和顾问一起选择已确认的本地活动；不预设任何参观。",
        "activity": "确认最新的游客信息后，可以考虑去{place}。",
        "open_activity": "确认细节后，选择一项无障碍的本地活动。",
        "verify": "开放时间、无障碍设施、交通和空位都需要确认。",
        "verify_access": "请确认无台阶通道、无障碍卫生间，以及从下车点到入口的距离。",
    },
}


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
    text = DRAFT_TEXT[data.language]
    # Limited mobility makes every day gentle, whatever pace was asked for, and adds an access check.
    mobility = bool(data.access_needs.get("wheelchair") not in (None, "NONE") or data.access_needs.get("step_free")
                    or (data.access_needs.get("max_walk_meters") or 10_000) <= 500)
    gentle = mobility or data.travel_pace == "RELAXED"
    rest_note = text["rest_relaxed"] if gentle else text["rest_standard"]
    verification = [text["verify_access"]] if mobility else [text["verify"]]
    for day_number in range(1, min(data.duration_days, 14) + 1):
        attraction = names[day_number - 1] if day_number <= len(names) else None
        place = catalog.get(attraction or "", {})
        shown = local_name(attraction, data.language) if attraction else None
        title = (text["title"].format(place=shown) if attraction else
                 text["open_titles"][(day_number - len(names) - 1) % 3])
        note = text["note"].format(place=shown) if attraction else text["open_note"]
        activities = [text["activity"].format(place=shown) if attraction else text["open_activity"]]
        days.append(DraftDay(day_number=day_number, title=title, note=note, attraction=attraction,
                             activities=activities, rest_note=rest_note, intensity="LOW" if gentle else "MODERATE",
                             verification_notes=verification,
                             source_urls=[place["source_url"]] if place.get("source_url") else []))
    return days


def search_suppliers(requirements: RequirementOutput, supplier) -> list[OfferData]:
    """Ask the supplier for offers matching complete requirements; claims come from supplier attributes."""
    if validate_requirements(requirements):
        raise ValueError("Requirements must be complete before supplier discovery")
    offers = supplier.search(requirements.destination, requirements.traveler_count, requirements.duration_days,
                             requirements.departure_date)
    return [OfferData(
        product_id=offer.product_id, total_amount=offer.total_amount, currency=offer.currency,
        includes=offer.includes,
        claims={claim: offer.attributes.get(attribute) for claim, (attribute, _) in CLAIM_ATTRIBUTES.items()},
        expires_at=offer.valid_until, supplier_offer_ref=offer.offer_ref, name=offer.name,
        attributes=offer.attributes, cancellation_policy=offer.cancellation_policy,
        evidence=[EvidenceData(claim_type=item.claim_type, source=item.source, polarity=item.polarity,
                               strength=item.strength, reference=item.reference, detail=item.detail, url=item.url)
                  for item in offer.evidence],
    ) for offer in offers if offer.currency == requirements.currency]


# "meals" only counts when the traveler has dietary needs; scores are normalised by the weights in play.
RANKING_WEIGHTS = {"accessibility": 0.35, "price": 0.25, "pace": 0.15, "flexibility": 0.15, "rating": 0.10, "meals": 0.10}
# Each verifiable claim, the supplier attribute stating it, and its short name in ranking codes.
CLAIM_ATTRIBUTES = {"lift_serves_all_guest_floors": ("lift_all_floors", "LIFT"),
                    "step_free_entry": ("step_free_entry", "STEP_FREE"),
                    "accessible_bathroom": ("accessible_bathroom", "BATHROOM")}
NO_ACCESS_CLAIM = "no_access_need"
SHORT_WALK_METERS = 200  # At or below this, offers that need a lot of walking are unsuitable.


def required_claims(elevator_required: bool, needs: dict | None = None) -> list[str]:
    """The access claims an offer must prove for this traveler, from their words and their saved needs."""
    needs = needs or {}
    wheelchair = needs.get("wheelchair", "NONE")
    uses_wheels = wheelchair in {"MANUAL", "POWER"}
    claims = []
    if elevator_required or wheelchair != "NONE":
        claims.append("lift_serves_all_guest_floors")
    if elevator_required or needs.get("step_free") or uses_wheels:
        claims.append("step_free_entry")
    if needs.get("accessible_bathroom") or uses_wheels:
        claims.append("accessible_bathroom")
    return claims
PACE_FIT = {"RELAXED": {"LOW": 1.0, "MODERATE": 0.6, "HIGH": 0.2}, "STANDARD": {"LOW": 1.0, "MODERATE": 1.0, "HIGH": 0.6}}


def refund_percent(policy: list[dict], departure: date | None, today: date) -> int:
    """Refund owed under an offer's own policy when cancelling `today` for a trip leaving on `departure`."""
    if not departure:
        return 0
    days_before = (departure - today).days
    for rule in sorted(policy, key=lambda item: -item["days_before"]):
        if days_before >= rule["days_before"]:
            return int(rule["refund_percent"])
    return 0


def _claim_value(value) -> tuple[float, str]:
    return (1.0, "YES") if value is True else (0.0, "NO") if value is False else (0.5, "UNKNOWN")


def score_offer(offer: OfferData, data: RankingInput) -> tuple[bool, float, list[dict]]:
    """A 0-100 score from supplier-stated features, with the reason behind every factor."""
    attributes, needs = offer.attributes, data.needs
    factors: list[dict] = []
    eligible = True
    if offer.currency != data.currency or offer.total_amount > data.budget:
        eligible = False
        factors.append({"factor": "budget", "code": "OVER_BUDGET", "value": 0.0, "weight": 0})
    if offer.product_id in data.excluded_ids:
        eligible = False
        factors.append({"factor": "evidence", "code": "EXCLUDED_BY_EVIDENCE", "value": 0.0, "weight": 0})
    claims = required_claims(data.elevator_required, needs)
    if claims:
        values = [(_claim_value(attributes.get(CLAIM_ATTRIBUTES[c][0])), CLAIM_ATTRIBUTES[c][1]) for c in claims]
        access = sum(value for (value, _), _ in values) / len(values)
        access_code = "_".join(f"{label}_{code}" for (_, code), label in values)
    else:
        access, access_code = 1.0, "NO_ACCESS_NEED"
    price = max(0.0, 1 - float(offer.total_amount / data.budget)) if data.budget > 0 else 0.0
    walking = attributes.get("walking_level", "MODERATE")
    max_walk = needs.get("max_walk_meters")
    pace_need = "RELAXED" if max_walk is not None and max_walk <= 500 else data.travel_pace
    pace, pace_code = PACE_FIT[pace_need].get(walking, 0.6), f"WALKING_{walking}"
    if max_walk is not None and max_walk <= SHORT_WALK_METERS and walking == "HIGH":
        eligible, pace, pace_code = False, 0.0, "TOO_MUCH_WALKING"
    free_days = max((rule["days_before"] for rule in offer.cancellation_policy if rule["refund_percent"] >= 100), default=None)
    flexibility = 1.0 if free_days is not None and free_days <= 7 else 0.7 if free_days is not None else 0.2
    rating = float(attributes.get("rating", 3.5)) / 5
    scored = [("accessibility", access, access_code),
              ("price", price, f"BUDGET_SHARE_{round(float(offer.total_amount / data.budget) * 100)}" if data.budget else "NO_BUDGET"),
              ("pace", pace, pace_code),
              ("flexibility", flexibility, f"FREE_CANCEL_{free_days}D" if free_days is not None else "NO_FREE_CANCEL"),
              ("rating", rating, f"RATING_{attributes.get('rating', 'NA')}")]
    if needs.get("dietary"):
        wanted = set(needs["dietary"])
        served = wanted & set(attributes.get("dietary_options", []))
        scored.append(("meals", len(served) / len(wanted), f"DIET_{len(served)}_OF_{len(wanted)}"))
    for name, value, code in scored:
        factors.append({"factor": name, "code": code, "value": round(value, 3), "weight": RANKING_WEIGHTS[name]})
    weighted = [f for f in factors if f["weight"]]
    score = round(100 * sum(f["weight"] * f["value"] for f in weighted) / sum(f["weight"] for f in weighted), 2)
    return eligible, score, factors


def compare_offers(data: RankingInput) -> RankingOutput:
    ranked = []
    for offer in data.offers:
        eligible, score, factors = score_offer(offer, data)
        ranked.append(RankedOffer(product_id=offer.product_id, eligible=eligible, score=score, factors=factors))
    ranked.sort(key=lambda item: (not item.eligible, -item.score, item.product_id))
    return RankingOutput(ordered_product_ids=[item.product_id for item in ranked if item.eligible], ranked=ranked)


def verify_evidence(sources: list[EvidenceData], claim_type: str) -> AssessmentData:
    """Judge one claim from independent sources: any strong contradiction blocks, strong support passes."""
    relevant = [item for item in sources if item.claim_type == claim_type]
    refs = [item.reference for item in relevant]
    if any(item.polarity == "CONTRADICT" for item in relevant):
        return AssessmentData(verdict="BLOCK", reason_code="ACCESSIBILITY_CONFLICT", source_refs=refs)
    if any(item.polarity == "SUPPORT" and item.strength == "STRONG" for item in relevant):
        return AssessmentData(verdict="PASS", reason_code="SOURCE_SUPPORT", source_refs=refs)
    reason = "INSUFFICIENT_FLOOR_COVERAGE" if claim_type == "lift_serves_all_guest_floors" else "INSUFFICIENT_EVIDENCE"
    return AssessmentData(verdict="REVIEW", reason_code=reason, source_refs=refs)


def assess_offer(sources: list[EvidenceData], claims: list[str]) -> dict[str, AssessmentData]:
    """One verdict per claim the traveler needs; with no access need the offer passes outright."""
    if not claims:
        return {NO_ACCESS_CLAIM: AssessmentData(verdict="PASS", reason_code="NO_ACCESSIBILITY_CONSTRAINT",
                                                source_refs=[item.reference for item in sources])}
    return {claim: verify_evidence(sources, claim) for claim in claims}


def rerank_offers(data: RankingInput, verdicts: dict[str, str]) -> RankingOutput:
    """Rank again with every offer that failed or could not settle verification excluded."""
    excluded = [*data.excluded_ids, *(product for product, verdict in verdicts.items() if verdict in {"BLOCK", "REVIEW"})]
    return compare_offers(data.model_copy(update={"excluded_ids": list(dict.fromkeys(excluded))}))


def generate_review(data: ReviewInput) -> ReviewOutput:
    return ReviewOutput(summary=f"Order {data.order_id} for offer {data.offer_id} was confirmed for case {data.case_id}.")
