"""Deterministic New Zealand destination and attraction vocabulary."""

import re
import unicodedata


DESTINATIONS = {
    "Auckland": ("auckland", "奥克兰", "奧克蘭"),
    "Queenstown": ("queenstown", "皇后镇", "皇后鎮"),
    "Rotorua": ("rotorua", "罗托鲁瓦", "羅托魯瓦"),
    "Wellington": ("wellington", "惠灵顿", "惠靈頓"),
    "Christchurch": ("christchurch", "基督城"),
    "Taupō": ("taupo", "taupō", "陶波"),
}

ATTRACTIONS = {
    "Auckland": {"Sky Tower": ("sky tower", "天空塔"), "Auckland Harbour": ("auckland harbour", "奥克兰港", "奧克蘭港"),
                 "Auckland War Memorial Museum": ("auckland museum", "war memorial museum", "奥克兰博物馆", "奧克蘭博物館", "museum", "博物馆", "博物館")},
    "Queenstown": {"Lake Wakatipu": ("lake wakatipu", "wakatipu", "瓦卡蒂普湖", "瓦卡提普湖", "lake views", "湖景"),
                   "Skyline Queenstown": ("skyline queenstown", "skyline gondola", "缆车", "纜車")},
    "Rotorua": {"Lake Rotorua": ("lake rotorua", "罗托鲁瓦湖", "羅托魯瓦湖"),
                "Wai-O-Tapu": ("wai-o-tapu", "怀奥塔普", "懷奧塔普"),
                "Polynesian Spa": ("polynesian spa", "hot spring", "hot pool", "温泉", "溫泉", "泡汤", "泡湯")},
    "Wellington": {"Wellington Harbour": ("wellington harbour", "惠灵顿港", "惠靈頓港")},
    "Christchurch": {"Christchurch Botanic Gardens": ("botanic gardens", "植物园", "植物園")},
    "Taupō": {"Lake Taupō": ("lake taupo", "lake taupō", "陶波湖"),
              "Huka Falls": ("huka falls", "胡卡瀑布")},
}


ATTRACTION_CATALOG = {
    "Auckland": {
        "Auckland Harbour": {"themes": ["city", "scenery"], "source_url": "https://www.newzealand.com/au/auckland-central/"},
        "Sky Tower": {"themes": ["city", "scenery"], "source_url": "https://www.newzealand.com/nz/auckland%2Badventure/"},
        "Auckland War Memorial Museum": {"themes": ["culture", "city"], "source_url": "https://www.newzealand.com/au/auckland-central/"},
    },
    "Queenstown": {
        "Lake Wakatipu": {"themes": ["lake", "scenery"], "source_url": "https://www.newzealand.com/nz/feature/lake-wakatipu/"},
        "Skyline Queenstown": {"themes": ["scenery", "gondola"], "source_url": "https://www.newzealand.com/nz/plan/business/skyline-queenstown--gondola/"},
    },
    "Rotorua": {
        "Lake Rotorua": {"themes": ["lake", "scenery"], "source_url": "https://www.newzealand.com/uk/rotorua-central/"},
        "Wai-O-Tapu": {"themes": ["geothermal", "nature"], "source_url": "https://www.newzealand.com/nz/plan/business/wai-o-tapu-thermal-wonderland/"},
        "Polynesian Spa": {"themes": ["hot-springs", "wellness"], "source_url": "https://www.newzealand.com/us/plan/business/polynesian-spa/"},
    },
    "Taupō": {
        "Lake Taupō": {"themes": ["lake", "nature"], "source_url": "https://www.newzealand.com/us/feature/lake-taupo-attractions/"},
        "Huka Falls": {"themes": ["waterfall", "nature"], "source_url": "https://www.newzealand.com/us/feature/huka-falls/"},
    },
}

FOREIGN_DESTINATIONS = ("china", "中国", "中國", "hangzhou", "杭州", "beijing", "北京", "shanghai", "上海",
                        "japan", "日本", "tokyo", "东京", "東京", "kyoto", "京都", "osaka", "大阪",
                        "australia", "澳大利亚", "澳洲", "sydney", "悉尼", "melbourne", "墨尔本", "墨爾本",
                        "paris", "巴黎", "london", "伦敦", "倫敦",
                        "singapore", "新加坡", "new york", "纽约", "紐約", "los angeles", "洛杉矶", "洛杉磯")


def _fold(value: str) -> str:
    return unicodedata.normalize("NFKD", value).lower()


def _contains(text: str, alias: str) -> bool:
    folded = _fold(alias)
    return bool(re.search(rf"(?<![a-z]){re.escape(folded)}(?![a-z])", text)) if folded.isascii() else folded in text


def resolve_destination(value: str) -> tuple[str | None, str]:
    """Return canonical destination and SUPPORTED, OUTSIDE_NZ, or UNKNOWN."""
    text = _fold(value)
    if any(_contains(text, alias) for alias in FOREIGN_DESTINATIONS):
        return None, "OUTSIDE_NZ"
    for destination, aliases in DESTINATIONS.items():
        if any(_contains(text, alias) for alias in aliases):
            return destination, "SUPPORTED"
    return None, "UNKNOWN"


def resolve_attractions(request: str, destination: str | None) -> list[str]:
    text = _fold(request)
    return [name for name, aliases in ATTRACTIONS.get(destination or "", {}).items()
            if any(_contains(text, alias) for alias in aliases)]
