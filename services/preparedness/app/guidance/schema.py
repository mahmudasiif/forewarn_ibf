"""Guideline schema + constants — ported from src/lib/guidelineSchema.ts.

Holds the seven impact sectors, bilingual labels, the NEAP levels, the impact
summary table headers, the impact-tier rubric, and the Gemini structured-output
schema (copied verbatim so the model returns the same shape as the original app).
"""
from __future__ import annotations

Lang = str  # "bn" | "en"

IMPACT_TIERS = ["minimal", "low", "moderate", "high", "severe"]

IMPACT_CATEGORIES = [
    "populationAndHouse",
    "infrastructurePolder",
    "agriculture",
    "livestockFisheries",
    "livelihood",
    "healthDisease",
    "utilityService",
]

# Human-readable sector labels shown on the cards, English key -> label.
IMPACT_SECTOR_CARDS: list[tuple[str, str]] = [
    ("Population and House", "populationAndHouse"),
    ("Infrastructure/Polder", "infrastructurePolder"),
    ("Agriculture", "agriculture"),
    ("Livestock + Fisheries", "livestockFisheries"),
    ("Livelihood", "livelihood"),
    ("Health/Disease", "healthDisease"),
    ("Utility service", "utilityService"),
]

CATEGORY_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "populationAndHouse": "Population and House",
        "infrastructurePolder": "Infrastructure/Polder",
        "agriculture": "Agriculture",
        "livestockFisheries": "Livestock + Fisheries",
        "livelihood": "Livelihood",
        "healthDisease": "Health/Disease",
        "utilityService": "Utility service",
    },
    "bn": {
        "populationAndHouse": "জনসংখ্যা ও ঘরবাড়ি",
        "infrastructurePolder": "অবকাঠামো/পোল্ডার",
        "agriculture": "কৃষি",
        "livestockFisheries": "গবাদিপশু ও মৎস্য",
        "livelihood": "জীবিকা",
        "healthDisease": "স্বাস্থ্য/রোগ",
        "utilityService": "উপযোগ সেবা",
    },
}

LEVEL_KEYS = ["community", "institutional"]


def clamp_percentage(value) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN
        return None
    return max(0.0, min(100.0, v))


def _band_index(value, thresholds: list[float]) -> int:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0
    if v != v:
        return 0
    index = 0
    for t in thresholds:
        if v >= t:
            index += 1
        else:
            break
    return index


def compute_impact_tier(
    *,
    wind_kmh=None,
    surge_m=None,
    affected_pct=None,
    full_damage_types: list[str] | None = None,
) -> str:
    wind = _band_index(wind_kmh, [62, 89, 118, 167])
    surge = _band_index(surge_m, [0.3, 0.9, 1.8, 3.0])
    affected = _band_index(affected_pct, [10, 25, 45, 70])
    damage_score = [0, 2, 3, 4]
    n = len(full_damage_types or [])
    damage = damage_score[min(len(damage_score) - 1, n)]
    score = max(wind, surge, affected, damage)
    return IMPACT_TIERS[min(len(IMPACT_TIERS) - 1, max(0, score))]


def impact_table_headers(rainfall_window_hours: float | None = None) -> list[str]:
    if isinstance(rainfall_window_hours, (int, float)) and rainfall_window_hours and rainfall_window_hours > 0:
        rain = f"Accumulated rainfall ({round(rainfall_window_hours)} Hours)"
    else:
        rain = "Accumulated rainfall (mm)"
    return [
        "Administrative Boundary",
        "Avg wind speed (km/h)",
        "Max surge (m)",
        rain,
        "Total Population",
        "Total",
        "Male",
        "Female",
        "0–4 Years",
        "5 to 19 Years",
        "Age 60+",
        "Potential affected house",
    ]


_SECTOR_KEYS = list(IMPACT_CATEGORIES)
_IMPACT_BULLETS = {"type": "array", "items": {"type": "string"}}
_ADVISORY_BULLETS = {"type": "array", "items": {"type": "string"}}
_ADVISORY_SECTORS = {
    "type": "object",
    "description": (
        "Actionable advice, one bullet list per sector — the same seven sectors as majorImpact. "
        "Every bullet is an INSTRUCTION (what to do), never a restatement of what may happen."
    ),
    "properties": {k: _ADVISORY_BULLETS for k in _SECTOR_KEYS},
    "required": list(_SECTOR_KEYS),
}

GEMINI_NARRATIVE_SCHEMA = {
    "type": "object",
    "properties": {
        "majorImpact": {
            "type": "object",
            "description": (
                "What the cyclone may do to the area, per template row. Plain bullet lists, "
                "hazard-driven likelihood language ('may', 'could') — impact is one physical "
                "reality and is NOT split by community/institutional level, and must NOT contain "
                "instructions or recommendations."
            ),
            "properties": {k: _IMPACT_BULLETS for k in _SECTOR_KEYS},
            "required": list(_SECTOR_KEYS),
        },
        "advisories": {
            "type": "object",
            "description": (
                "What to DO about the impact, split by NEAP level then by the same seven sectors "
                "as majorImpact. `community` = what households and ordinary people do themselves; "
                "`institutional` = what government departments, union/upazila administration, "
                "operators and agencies do, including anything that requires organising, listing, "
                "ordering or resourcing an evacuation."
            ),
            "properties": {"community": _ADVISORY_SECTORS, "institutional": _ADVISORY_SECTORS},
            "required": ["community", "institutional"],
        },
    },
    "required": ["majorImpact", "advisories"],
}
