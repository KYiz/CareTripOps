"""What the travel guide says: intent cues and replies in English and Chinese."""

# English and Chinese (simplified and traditional) cues, checked in this order.
ACCESS_WORDS = ("lift", "elevator", "wheelchair", "stairs", "step-free", "step free", "accessible", "bathroom", "shower",
                "电梯", "電梯", "轮椅", "輪椅", "台阶", "台階", "楼梯", "樓梯", "无障碍", "無障礙", "卫生间", "衛生間", "淋浴")
CHANGE_WORDS = ("change", "switch", "cheaper", "another", "换", "換", "便宜")
PACKAGE_WORDS = ("hotel", "accommodation", "price", "budget", "package", "booking", "payment", "transport", "cheaper",
                 "酒店", "住宿", "价格", "價格", "预算", "預算", "套餐", "预订", "預訂", "付款", "交通", "便宜")
REVISION_WORDS = ("change", "adjust", "skip", "tired", "rest", "slower", "too much", "modify",
                  "改", "调整", "調整", "跳过", "跳過", "累", "休息", "慢", "太多", "轻松", "輕鬆")
NEXT_WORDS = ("next", "after this", "following", "下一", "接下来", "接下來", "之后", "之後")

REPLIES = {
    "en": {
        "package": "A change to price, hotel, transport or package needs a new trip request and fresh verification. Your current approved offer and booking remain unchanged.",
        "revision": "I can prepare a gentler draft for you to review. This will not change a verified offer or booking.",
        "no_trip": "Start by telling us about your New Zealand trip. I can then use your trip details here.",
        "next": "Your illustrative next stop is {place}. Consider a rest before continuing.",
        "no_next": "There is no further attraction in this illustrative outline. You can take a break.",
        "place": "{place} is listed in your {destination} trip idea. I can help you review the next step or request a gentler draft. Visit details have not been verified.",
        "no_place": "Your {destination} trip is taking shape. Choose an attraction to ask about it.",
        "access": "At {stay}, these were checked against independent sources for you: {claims}. The sources are listed below.",
        "access_no_need": "You did not ask for access features, so none were checked at {stay}. A travel advisor can check one for you.",
        "access_none": "No stay has been chosen yet. Once an offer is verified, I can tell you exactly what was checked.",
        "clarified": "I saved those details and am continuing your trip plan.",
        "still_need": "Thank you. I still need: {fields}.",
        "outside_nz": "This demo supports New Zealand destinations only.",
        "model_limit": "The model call limit was reached. Please use the text form.",
        "model_failed": "Gemini could not validate the spoken details. Please retry or use text.",
        "two_destinations": "I heard different destinations. Please confirm one destination in text.",
    },
    "zh": {
        "package": "更改价格、酒店、交通或套餐需要新建行程并重新核验。你当前已批准的报价和预订保持不变。",
        "revision": "我可以准备一份更轻松的草稿供你确认。这不会改变已核验的报价或预订。",
        "no_trip": "先告诉我你的新西兰旅行计划，我就能根据行程信息帮你。",
        "next": "示意行程中的下一站是{place}。继续之前可以先休息一下。",
        "no_next": "示意行程里没有更多景点了，可以好好休息一下。",
        "place": "{place}在你的{destination}行程灵感里。我可以帮你看看下一步，或者准备更轻松的草稿。具体参观信息尚未核实。",
        "no_place": "你的{destination}行程正在成形。选一个景点来问问我吧。",
        "access": "{stay}的以下条件已经通过独立来源为你核验：{claims}。来源列在下面。",
        "access_no_need": "你没有提出无障碍需求，所以{stay}没有核验相关设施。旅行顾问可以帮你确认。",
        "access_none": "还没有选定住宿。报价核验后，我可以告诉你具体核验了哪些条件。",
        "clarified": "这些信息我已经保存，正在继续规划你的行程。",
        "still_need": "谢谢！我还需要：{fields}。",
        "outside_nz": "本演示只支持新西兰境内的目的地。",
        "model_limit": "模型调用次数已用完，请改用文字表单。",
        "model_failed": "Gemini 无法确认你说的信息，请重试或改用文字。",
        "two_destinations": "我听到了不同的目的地，请用文字确认一个目的地。",
    },
}
CLAIM_NAMES = {
    "en": {"lift_serves_all_guest_floors": "a lift to every guest floor", "step_free_entry": "step-free entry",
           "accessible_bathroom": "an accessible bathroom"},
    "zh": {"lift_serves_all_guest_floors": "电梯可到达所有客房楼层", "step_free_entry": "无台阶入口",
           "accessible_bathroom": "无障碍卫浴"},
}
FIELD_NAMES = {"zh": {"destination": "目的地", "departure_date": "出发日期", "traveler_count": "人数",
                      "duration_days": "天数", "budget": "预算", "currency": "币种"}}
GENTLER_NOTE = {
    "en": "Gentler draft: leave time for a rest before this activity. Timing and availability require confirmation.",
    "zh": "更轻松的安排：参加这个活动前先留出休息时间。时间和空位仍需确认。",
}


def language_of(header: str | None) -> str:
    """The traveler's language from Accept-Language: Chinese when it leads, English otherwise."""
    return "zh" if (header or "").strip().lower().startswith("zh") else "en"


def reply_text(lang: str, key: str, **values) -> str:
    return REPLIES[lang][key].format(**values)


def field_names(lang: str, fields: list[str]) -> str:
    names = [FIELD_NAMES.get(lang, {}).get(field, field.replace("_", " ")) for field in fields]
    return ("、" if lang == "zh" else ", ").join(names)


def classify_intent(message: str) -> str:
    lowered = message.casefold()
    if any(word in lowered for word in ACCESS_WORDS) and not any(word in lowered for word in CHANGE_WORDS):
        return "ACCESS_QUESTION"
    if any(word in lowered for word in PACKAGE_WORDS):
        return "PACKAGE_CHANGE"
    if any(word in lowered for word in REVISION_WORDS):
        return "REVISION"
    if any(word in lowered for word in NEXT_WORDS):
        return "NEXT_ACTIVITY"
    return "ATTRACTION_QUESTION"
