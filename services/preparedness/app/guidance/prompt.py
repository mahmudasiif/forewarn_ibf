"""Structured guideline generation — ported from src/app/api/guideline/route.ts.

Builds the bilingual narrative prompt from an area's analysis context + the
cyclone track + NEAP action context + RAG grounding, calls Gemini with the
structured schema, then normalises/deduplicates the result and assembles the
GuidelineDocument. Falls back to a complete deterministic narrative if the LLM is
unavailable. Prompt strings, rubrics and the deterministic fallback are copied
verbatim from the handover so output matches the original app.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.guidance import gemini, neap as neap_mod, rag
from app.guidance.schema import (
    CATEGORY_LABELS,
    GEMINI_NARRATIVE_SCHEMA,
    IMPACT_CATEGORIES,
    LEVEL_KEYS,
    clamp_percentage,
    compute_impact_tier,
)

AVG_HOUSEHOLD_SIZE = 4.06

HOUSE_LABELS_BY_LANG = {
    "bn": {"Kancha": "কাঁচা", "Semi-pucca": "আধা-পাকা", "Pucca": "পাকা"},
    "en": {"Kancha": "Kancha", "Semi-pucca": "Semi-pucca", "Pucca": "Pucca"},
}

DAMAGE_LIKELIHOOD = {
    "bn": {"low": "ক্ষতির সম্ভাবনা কম", "some": "ক্ষতির সম্ভাবনা রয়েছে", "high": "ক্ষতির সম্ভাবনা বেশি"},
    "en": {"low": "Low likelihood of damage", "some": "Likelihood of damage", "high": "High likelihood of damage"},
}

T = {
    "bn": {
        "noData": "তথ্য নেই",
        "noAreaData": "এলাকা তথ্য নেই",
        "notModelled": "মডেল করা হয়নি (এই জেলার জন্য CCM কার্ভ নেই)",
        "people": "জন",
        "houses": "টি ঘর",
        "populationEstimate": "আবাসন-গণনা × ৪.০৬; আনুমানিক",
        "structuralResult": "কাঠামোভিত্তিক মডেল ফলাফল",
        "structuralNote": "প্রতিটি শ্রেণীর ফল আলাদা; কোনো একটি ক্ষতির মাত্রা সব ধরনের ঘরের জন্য প্রযোজ্য নয়।",
        "structuralMissing": "কাঠামোভিত্তিক ক্ষতির শ্রেণী পাওয়া যায়নি; মাঠ পর্যায়ে ঘরভিত্তিক যাচাই প্রয়োজন।",
        "house": "ঘর",
        "maxAt": "সর্বোচ্চ",
        "noSurge": "তথ্য নেই (storm-surge NetCDF দেওয়া হয়নি বা বৈধ মান নেই)",
        "noLandfall": "মডেল ট্র্যাকে স্থলভাগে প্রবেশ শনাক্ত হয়নি",
        "modelTime": "NetCDF মডেল সময়",
        "afterModelStart": "মডেল শুরুর",
        "hoursLater": "ঘণ্টা পর",
        "noReliableStart": "মডেল শুরুর আনুমানিক",
        "noReliableStartTail": "ঘণ্টা পর (NetCDF-এ নির্ভরযোগ্য শুরুর তারিখ/সময় নেই)",
        "towardCoast": "বাংলাদেশ উপকূলের দিকে",
        "relocateFull": "ঘর পূর্ণ-ক্ষতির উচ্চ সম্ভাবনার শ্রেণীতে থাকায় এসব ঘরের বাসিন্দাদের অগ্রাধিকার দিয়ে সরকারি নিরাপদ আশ্রয়ে সরিয়ে নিন।",
        "relocateNone": "কোনো ঘরের ধরন পূর্ণ-ক্ষতির উচ্চ সম্ভাবনার শ্রেণীতে নেই; তবে জলোচ্ছ্বাস/প্লাবন এলাকা ও সরকারি নির্দেশ অনুযায়ী ঝুঁকিপূর্ণ মানুষকে সরিয়ে নিন।",
    },
    "en": {
        "noData": "No data",
        "noAreaData": "Area not available",
        "notModelled": "Not modelled (no CCM curve for this district)",
        "people": "people",
        "houses": "houses",
        "populationEstimate": "housing count × 4.06; estimated",
        "structuralResult": "Structural model result",
        "structuralNote": "Each class is assessed separately; a damage level for one house type does not apply to all house types.",
        "structuralMissing": "No structural damage class was available; house-by-house field verification is needed.",
        "house": "houses",
        "maxAt": "highest at",
        "noSurge": "No data (storm-surge NetCDF not supplied, or no valid values)",
        "noLandfall": "No land entry detected on the model track",
        "modelTime": "NetCDF model time",
        "afterModelStart": "",
        "hoursLater": "hours after model start",
        "noReliableStart": "approximately",
        "noReliableStartTail": "hours after model start (the NetCDF has no reliable start date/time)",
        "towardCoast": "toward the Bangladesh coast",
        "relocateFull": "houses fall in the high-likelihood total-damage class; move residents of these houses to a government safe shelter as a priority.",
        "relocateNone": "No house type falls in the high-likelihood total-damage class; even so, move at-risk people according to surge/flood zoning and government instructions.",
    },
}

LEVEL_LABELS = {
    "bn": {"community": "কমিউনিটি পর্যায়", "institutional": "প্রাতিষ্ঠানিক পর্যায়"},
    "en": {"community": "Community level", "institutional": "Institutional level"},
}

_BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")


def tr(lang: str, key: str) -> str:
    return T.get(lang, {}).get(key) or T["bn"].get(key, "")


def house_label(lang: str, t: str) -> str:
    return HOUSE_LABELS_BY_LANG[lang].get(t, t)


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not (isinstance(v, float) and v != v)


def fmt(value, lang: str, digits: int = 1) -> str:
    if not _is_num(value):
        return tr(lang, "noData")
    return f"{float(value):.{digits}f}"


def na_if_empty(value, lang: str) -> str:
    v = (value or "").strip() if isinstance(value, str) else ""
    return v or tr(lang, "noData")


def num(n, lang: str, max_frac: int = 0) -> str:
    try:
        if max_frac:
            s = f"{float(n):,.{max_frac}f}"
        else:
            s = f"{round(float(n)):,}"
    except (TypeError, ValueError):
        return str(n)
    return s.translate(_BN_DIGITS) if lang == "bn" else s


def fmt_datetime(d: datetime, lang: str) -> str:
    try:
        local = d.astimezone(ZoneInfo("Asia/Dhaka"))
        s = local.strftime("%d %B %Y, %H:%M")
        return s.translate(_BN_DIGITS) if lang == "bn" else s
    except Exception:  # noqa: BLE001
        return d.isoformat()


def parse_model_time(value) -> datetime | None:
    if not value:
        return None
    v = value if re.search(r"(?:Z|[+-]\d\d:\d\d)$", value) else f"{value}Z"
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None


def analysis_level(ctx: dict) -> str:
    if ctx.get("admin_level"):
        return ctx["admin_level"]
    if ctx.get("union"):
        return "union"
    if ctx.get("upazila"):
        return "upazila"
    return "district"


def area_name(ctx: dict, lang: str = "bn") -> str:
    return (ctx.get("name") or ctx.get("union") or ctx.get("upazila") or ctx.get("district") or "").strip() or tr(lang, "noData")


def area_label(ctx: dict, lang: str = "bn") -> str:
    level = analysis_level(ctx)
    if level == "union":
        parts = [ctx.get("union") or ctx.get("name"), ctx.get("upazila"), ctx.get("district")]
    elif level == "upazila":
        parts = [ctx.get("upazila") or ctx.get("name"), ctx.get("district")]
    else:
        parts = [ctx.get("district") or ctx.get("name")]
    return ", ".join(p for p in parts if p) or tr(lang, "noData")


def record_place(record, lang: str) -> str:
    if not record:
        return tr(lang, "noAreaData")
    seen: list[str] = []
    for v in (record.get("union") or record.get("name"), record.get("upazila"), record.get("district")):
        if v and v not in seen:
            seen.append(v)
    return ", ".join(seen) or tr(lang, "noAreaData")


def is_full_damage(value) -> bool:
    return bool(re.search(r"\b(full|complete|total collapse)\b", value or "", re.I))


def damage_status(value, lang: str) -> str:
    text = (value or "").lower()
    L = DAMAGE_LIKELIHOOD[lang]
    if re.search(r"full|complete|total collapse", text):
        return L["high"]
    if re.search(r"partial|severe|roof loss|wall collapse|structural damage", text):
        return L["some"]
    if re.search(r"minor|no damage|none", text):
        return L["low"]
    return (value or "").strip() or tr(lang, "noData")


def full_damage_types(ctx: dict) -> list[str]:
    explicit = [x for x in (ctx.get("full_damage_house_types") or []) if x]
    if explicit:
        return explicit
    return [t for t, status in (ctx.get("expected_damage") or {}).items() if is_full_damage(status)]


def housing_damage_fact(ctx: dict, lang: str) -> str:
    sep = "—" if lang == "bn" else ": "
    parts = [
        f"{house_label(lang, t)} {tr(lang, 'house')}{sep}{damage_status(status, lang)}"
        for t, status in (ctx.get("expected_damage") or {}).items()
    ]
    if not parts:
        return tr(lang, "structuralMissing")
    end = "।" if lang == "bn" else "."
    return f"{tr(lang, 'structuralResult')}: {'; '.join(parts)}{end} {tr(lang, 'structuralNote')}"


def format_affected(count, pct, modelled, unit_key: str, lang: str) -> str:
    if not modelled or not _is_num(count):
        return tr(lang, "notModelled")
    n = num(round(float(count)), lang)
    bounded = clamp_percentage(pct)
    share = "" if bounded is None else f" ({num(bounded, lang, 1)}%)"
    return f"{n} {tr(lang, unit_key)}{share}"


def format_affected_demographic(count, modelled, lang: str) -> str:
    if not modelled or not _is_num(count):
        return tr(lang, "notModelled")
    return num(round(float(count)), lang)


def build_deterministic_fields(cyclone_name: str, ctx: dict, track: dict, lang: str, cyc: dict | None) -> dict:
    housing_numbers = ctx.get("housing_numbers") or {}
    total_houses = sum(v for v in housing_numbers.values() if _is_num(v))
    if _is_num(ctx.get("total_population")) and ctx["total_population"] > 0:
        area_population = round(ctx["total_population"])
    elif total_houses > 0:
        area_population = round(total_houses * AVG_HOUSEHOLD_SIZE)
    else:
        area_population = None

    available = bool(cyc and cyc.get("available"))
    cs = cyc.get("current_state") if available else None
    fs = cyc.get("forecast_state") if available else None
    cs = cs or {}
    fs = fs or {}
    wind_record = fs.get("max_wind_record")
    surge_record = fs.get("max_storm_surge_record")
    rain_record = fs.get("max_rain_record")

    max_wind = (wind_record or {}).get("wind_speed_kmh") if wind_record else fs.get("max_land_wind_kmh")
    max_surge = (surge_record or {}).get("storm_surge_m") if surge_record else fs.get("max_storm_surge_m")
    max_rain = (rain_record or {}).get("total_rainfall_mm") if rain_record else fs.get("max_rainfall_mm")
    demographic = ctx.get("affected_population_breakdown") or {}
    selected_surge = ctx["storm_surge_m"] if _is_num(ctx.get("storm_surge_m")) else None

    current_wind = cs.get("wind_speed_kmh")
    current_wind_label = (
        f"{current_wind:.1f} km/hr" if _is_num(current_wind) else f"{fmt(ctx.get('wind_speed_kmh'), lang)} km/hr"
    )

    forecast_time_label = na_if_empty(track.get("landfallTime"), lang)
    exact_landfall = parse_model_time(fs.get("time_iso"))
    lead_hours = fs.get("lead_time_hours")
    if exact_landfall:
        if _is_num(lead_hours):
            lead_suffix = re.sub(r"\s+", " ", f"; {tr(lang, 'afterModelStart')} {num(round(lead_hours), lang)} {tr(lang, 'hoursLater')}")
        else:
            lead_suffix = ""
        forecast_time_label = f"{fmt_datetime(exact_landfall, lang)} ({tr(lang, 'modelTime')}{lead_suffix})"
    elif _is_num(lead_hours):
        forecast_time_label = f"{tr(lang, 'noReliableStart')} {num(round(lead_hours), lang)} {tr(lang, 'noReliableStartTail')}"

    dir_base = cs.get("direction_en") if lang == "en" else cs.get("direction_bn")
    direction_label = dir_base or na_if_empty(track.get("direction"), lang)
    if dir_base and fs.get("landfall_district"):
        direction_label = f"{dir_base} — {tr(lang, 'towardCoast')}"
    location_label = (cs.get("location_label_en") if lang == "en" else cs.get("location_label_bn")) or na_if_empty(track.get("currentLocation"), lang)
    landfall_place = (fs.get("landfall_place_en") if lang == "en" else fs.get("landfall_place_bn")) or tr(lang, "noLandfall")

    return {
        "currentState": {
            "name": cyclone_name or tr(lang, "noData"),
            "category": cs.get("category_imd_en") or na_if_empty(track.get("category"), lang),
            "windSpeedKmh": current_wind_label,
            "direction": direction_label,
            "location": location_label,
        },
        "forecastState": {
            "landfallLocation": landfall_place,
            "windSpeed": (
                f"{max_wind:.1f} km/hr — {tr(lang, 'maxAt')}: {record_place(wind_record, lang)}"
                if _is_num(max_wind)
                else tr(lang, "noData")
            ),
            "stormSurge": (
                f"{max_surge:.2f} m — {tr(lang, 'maxAt')}: {record_place(surge_record, lang)}"
                if _is_num(max_surge)
                else tr(lang, "noSurge")
            ),
            "time": forecast_time_label,
            "category": fs.get("category_imd_en") or na_if_empty(track.get("category"), lang),
            "precipitation": (
                f"{max_rain:.1f} mm — {tr(lang, 'maxAt')}: {record_place(rain_record, lang)}"
                if _is_num(max_rain)
                else tr(lang, "noData")
            ),
        },
        "impactSummaryTable": [
            {
                "area": area_label(ctx, lang),
                "windSpeedKmh": fmt(ctx.get("wind_speed_kmh"), lang),
                "surgeM": f"{selected_surge:.2f}" if selected_surge is not None else tr(lang, "noData"),
                "precipitationMm": fmt(ctx.get("total_rainfall_mm"), lang),
                "totalPopulation": tr(lang, "noData") if area_population is None else num(area_population, lang),
                "affectedPopulation": format_affected(ctx.get("affected_people"), ctx.get("affected_people_pct"), ctx.get("impact_modelled"), "people", lang),
                "affectedMale": format_affected_demographic(demographic.get("male"), ctx.get("impact_modelled"), lang),
                "affectedFemale": format_affected_demographic(demographic.get("female"), ctx.get("impact_modelled"), lang),
                "affectedAge0To4": format_affected_demographic(demographic.get("age_0_4"), ctx.get("impact_modelled"), lang),
                "affectedAge5To19": format_affected_demographic(demographic.get("age_5_19"), ctx.get("impact_modelled"), lang),
                "affectedAge60Plus": format_affected_demographic(demographic.get("age_60_plus"), ctx.get("impact_modelled"), lang),
                "affectedHouseStructure": format_affected(ctx.get("affected_houses"), ctx.get("affected_houses_pct"), ctx.get("impact_modelled"), "houses", lang),
            }
        ],
    }


def wind_severity_guide(wind_kmh, lang: str) -> str:
    w = wind_kmh if _is_num(wind_kmh) else 0
    if lang == "en":
        if w <= 31:
            return "IMD class Low-pressure area (≤31 km/h): no cyclone-strength wind damage is expected; keep to rainfall and waterlogging effects and avoid any storm-damage wording."
        if w <= 49:
            return "IMD class Depression (32–49 km/h): only minor damage to weak roofing and branches and temporary waterlogging in low areas is possible; do not use major-destruction wording."
        if w <= 61:
            return "IMD class Deep Depression (50–61 km/h): loose roofing sheets, weak branches and local waterlogging may be affected; damage stays minor and localised."
        if w <= 88:
            return "IMD class Cyclonic Storm (62–88 km/h): partial damage to kancha roofing, weak trees and local power/communication is possible; do not say completely destroyed."
        if w <= 117:
            return "IMD class Severe Cyclonic Storm (89–117 km/h): serious disruption to weak kancha houses, trees, power lines and mobile service, plus flooding risk in low-lying areas."
        if w <= 166:
            return "IMD class Very Severe Cyclonic Storm (118–166 km/h): serious damage to kancha houses and weak roofs, trees/poles breaking, prolonged power and mobile outages, and possible surge/flooding."
        if w <= 221:
            return "IMD class Extremely Severe Cyclonic Storm (167–221 km/h): extreme wind damage is possible; even so, report damage for each house type strictly according to the structural model result."
        return "IMD class Super Cyclonic Storm (≥222 km/h): catastrophic wind damage is possible; even so, report damage for each house type strictly according to the structural model result."
    if w <= 31:
        return "IMD শ্রেণী নিম্নচাপ (≤৩১ কিমি/ঘণ্টা): ঘূর্ণিঝড়-মাত্রার বাতাসজনিত ক্ষতি প্রত্যাশিত নয়; কেবল বৃষ্টিপাত ও জলাবদ্ধতার প্রভাব লিখুন, ঝড়ের ক্ষয়ক্ষতির ভাষা ব্যবহার করবেন না।"
    if w <= 49:
        return "IMD শ্রেণী নিম্নচাপ/Depression (৩২–৪৯ কিমি/ঘণ্টা): কেবল দুর্বল ছাউনি ও ডালপালার সামান্য ক্ষতি এবং নিচু স্থানে সাময়িক জলাবদ্ধতা সম্ভাব্য; বড় ধ্বংসের ভাষা ব্যবহার করবেন না।"
    if w <= 61:
        return "IMD শ্রেণী গভীর নিম্নচাপ (৫০–৬১ কিমি/ঘণ্টা): আলগা টিনের ছাউনি, দুর্বল ডালপালা ও স্থানীয় জলাবদ্ধতা হতে পারে; ক্ষতি সীমিত ও স্থানীয় পর্যায়ে থাকবে।"
    if w <= 88:
        return "IMD শ্রেণী ঘূর্ণিঝড় (৬২–৮৮ কিমি/ঘণ্টা): কাঁচা ঘরের ছাউনি, দুর্বল গাছ ও স্থানীয় বিদ্যুৎ/যোগাযোগে আংশিক ক্ষতি সম্ভাব্য; সম্পূর্ণ বিধ্বস্ত বলবেন না।"
    if w <= 117:
        return "IMD শ্রেণী প্রবল ঘূর্ণিঝড় (৮৯–১১৭ কিমি/ঘণ্টা): দুর্বল কাঁচা ঘর, গাছ, বিদ্যুৎ লাইন ও মোবাইল সেবায় গুরুতর বিঘ্ন এবং নিচু এলাকায় প্লাবনের ঝুঁকি।"
    if w <= 166:
        return "IMD শ্রেণী অতি প্রবল ঘূর্ণিঝড় (১১৮–১৬৬ কিমি/ঘণ্টা): কাঁচা ঘর ও দুর্বল ছাদে গুরুতর ক্ষতি, গাছ/খুঁটি ভাঙা, দীর্ঘ বিদ্যুৎ-মোবাইল বিভ্রাট ও জলোচ্ছ্বাস/প্লাবন সম্ভাব্য।"
    if w <= 221:
        return "IMD শ্রেণী চরম প্রবল ঘূর্ণিঝড় (১৬৭–২২১ কিমি/ঘণ্টা): চরম বাতাসজনিত ক্ষতি সম্ভাব্য; তবু প্রতিটি ঘরের ক্ষতি কেবল কাঠামোভিত্তিক মডেল ফল অনুযায়ী আলাদাভাবে লিখবেন।"
    return "IMD শ্রেণী সুপার ঘূর্ণিঝড় (≥২২২ কিমি/ঘণ্টা): ভয়াবহ বাতাসজনিত ক্ষতি সম্ভাব্য; তবু প্রতিটি ঘরের ক্ষতি কেবল কাঠামোভিত্তিক মডেল ফল অনুযায়ী আলাদাভাবে লিখবেন।"


def impact_tier_for(ctx: dict) -> str:
    return compute_impact_tier(
        wind_kmh=ctx.get("wind_speed_kmh"),
        surge_m=ctx.get("storm_surge_m"),
        affected_pct=ctx.get("affected_people_pct"),
        full_damage_types=full_damage_types(ctx),
    )


def impact_tier_guide(tier: str, lang: str) -> str:
    en = {
        "minimal": "MINIMAL impact. Monitoring and information only: follow the bulletin, keep phones charged, know where the nearest shelter is. Do NOT recommend evacuation, shelter activation, early harvesting, moving livestock, or relocating assets — nothing here is at risk yet.",
        "low": "LOW impact. Readiness only: secure loose roofing sheets and yard items, keep documents in a waterproof bag, keep dry food and medicine to hand, tie down weak trees. Do NOT recommend mass evacuation, opening shelters, harvesting crops early, or emptying fish enclosures — the forecast does not justify that level of disruption.",
        "moderate": "MODERATE impact. Protective action: strengthen kancha and semi-pucca roofing, move livestock and poultry to raised ground or a killa, stock fodder and safe water, ready the shelters and their supplies, and move only the most exposed households — those in the Full-damage house types and in low-lying or riverbank locations. Harvest only crops that are already mature; do NOT recommend cutting an immature crop or a blanket area-wide evacuation.",
        "high": "HIGH impact. Full protective response: complete evacuation from coastal, riverbank and low-lying areas on the official signal, open and staff all shelters, harvest mature crops and net or harvest fish and shrimp enclosures, move livestock to killas, and pre-position relief, medical and restoration teams.",
        "severe": "SEVERE impact. Maximum-scale response: pre-emptive full evacuation ahead of the signal, all shelters open and staffed with protection and medical cover, harvest or write off standing crops, evacuate livestock, and stage search-and-rescue, relief and utility-restoration capacity before landfall.",
    }
    bn = {
        "minimal": "প্রভাব: খুবই কম (MINIMAL)। শুধু পর্যবেক্ষণ ও তথ্য: বুলেটিন অনুসরণ করুন, মোবাইল চার্জ রাখুন, নিকটবর্তী আশ্রয়কেন্দ্র চিনে রাখুন। সরিয়ে নেওয়া, আশ্রয়কেন্দ্র চালু করা, আগাম ফসল কাটা, গবাদিপশু সরানো বা মালামাল স্থানান্তরের পরামর্শ দেবেন না — এই পূর্বাভাসে এসবের প্রয়োজন নেই।",
        "low": "প্রভাব: কম (LOW)। শুধু প্রস্তুতি: আলগা টিনের চাল ও উঠানের জিনিস বেঁধে রাখুন, কাগজপত্র ওয়াটারপ্রুফ ব্যাগে রাখুন, শুকনো খাবার ও ওষুধ হাতের কাছে রাখুন, দুর্বল গাছ বেঁধে দিন। ব্যাপক সরিয়ে নেওয়া, আশ্রয়কেন্দ্র খোলা, আগাম ফসল কাটা বা মাছের ঘের খালি করার পরামর্শ দেবেন না — পূর্বাভাস এত বড় পদক্ষেপের যৌক্তিকতা দেয় না।",
        "moderate": "প্রভাব: মাঝারি (MODERATE)। সুরক্ষামূলক পদক্ষেপ: কাঁচা ও আধা-পাকা ঘরের ছাউনি শক্ত করুন, গবাদিপশু ও হাঁস-মুরগি উঁচু স্থানে বা কিল্লায় সরান, পশুখাদ্য ও নিরাপদ পানি মজুত করুন, আশ্রয়কেন্দ্র ও রসদ প্রস্তুত রাখুন, এবং কেবল সবচেয়ে ঝুঁকিপূর্ণ পরিবারগুলোকে — পূর্ণ-ক্ষতির শ্রেণীর ঘর এবং নিচু বা নদীতীরবর্তী এলাকার বাসিন্দাদের — সরিয়ে নিন। কেবল পরিপক্ব ফসল কাটার কথা বলুন; অপরিপক্ব ফসল কাটা বা পুরো এলাকা খালি করার পরামর্শ দেবেন না।",
        "high": "প্রভাব: বেশি (HIGH)। পূর্ণ সুরক্ষামূলক সাড়া: সরকারি সংকেত অনুযায়ী উপকূল, নদীতীর ও নিচু এলাকা থেকে সম্পূর্ণ সরিয়ে নিন, সব আশ্রয়কেন্দ্র খুলে জনবল দিন, পরিপক্ব ফসল কেটে নিন ও মাছ-চিংড়ির ঘেরে জাল দিন বা ধরে ফেলুন, গবাদিপশু কিল্লায় সরান, এবং ত্রাণ, চিকিৎসা ও পুনরুদ্ধার দল আগেভাগে মোতায়েন করুন।",
        "severe": "প্রভাব: ভয়াবহ (SEVERE)। সর্বোচ্চ মাত্রার সাড়া: সংকেতের আগেই আগাম পূর্ণ সরিয়ে নেওয়া, সব আশ্রয়কেন্দ্র সুরক্ষা ও চিকিৎসা সহায়তাসহ চালু, মাঠের ফসল কেটে নেওয়া, গবাদিপশু সরানো, এবং ল্যান্ডফলের আগেই উদ্ধার, ত্রাণ ও ইউটিলিটি পুনরুদ্ধারের সক্ষমতা প্রস্তুত রাখা।",
    }
    return (en if lang == "en" else bn)[tier]


def build_narrative_prompt(cyclone_name: str, ctx: dict, rag_context: str, neap: dict, lang: str, cyc: dict | None) -> str:
    available = bool(cyc and cyc.get("available"))
    cs = (cyc.get("current_state") if available else None) or {}
    fs = (cyc.get("forecast_state") if available else None) or {}
    level = analysis_level(ctx)
    full_types = full_damage_types(ctx)
    tier = impact_tier_for(ctx)
    bn = lang == "bn"
    damage_lines = "; ".join(
        f"{house_label(lang, t)}: {damage_status(status, lang)} ({status})"
        for t, status in (ctx.get("expected_damage") or {}).items()
    ) or tr(lang, "noData")
    full_damage_line = ", ".join(house_label(lang, t) for t in full_types) if full_types else ("কোনোটিই নয়" if bn else "none")

    if bn:
        L = {"metric": "সূচক", "value": "যাচাইকৃত/গণিত মান", "name": "ঘূর্ণিঝড়ের নাম", "lvl": "বিশ্লেষণের স্তর",
             "area": "নির্বাচিত এলাকা", "members": "সদস্য ইউনিয়ন", "risk": "ঝুঁকি শ্রেণী",
             "wind": "এলাকায় গড় বাতাস", "rain": "এলাকায় মোট সঞ্চিত বৃষ্টিপাতের সর্বোচ্চ",
             "surge": "এলাকায় জলোচ্ছ্বাসের সর্বোচ্চ", "housing": "আবাসন শতাংশ",
             "dmg": "ঘরের ধরনভিত্তিক ক্ষতির সম্ভাবনা", "full": "উচ্চ সম্ভাবনার (Full) শ্রেণীর ঘর",
             "cur": "বর্তমান অবস্থান/তীব্রতা", "path": "গতিপথ", "land": "প্রথম স্থলভাগ-স্পর্শ",
             "mw": "সর্বোচ্চ স্থলভাগের বাতাস", "ms": "সর্বোচ্চ জলোচ্ছ্বাস", "mr": "সর্বোচ্চ বৃষ্টিপাত", "hrs": "ঘণ্টা"}
    else:
        L = {"metric": "Indicator", "value": "Verified / computed value", "name": "Cyclone name", "lvl": "Analysis level",
             "area": "Selected area", "members": "Member unions", "risk": "Risk class",
             "wind": "Area average wind", "rain": "Area max accumulated rainfall",
             "surge": "Area max storm surge", "housing": "Housing share",
             "dmg": "Damage likelihood by house type", "full": "House types in the high-likelihood (Full) class",
             "cur": "Current position / intensity", "path": "Track direction", "land": "First landfall point",
             "mw": "Max wind over land", "ms": "Max storm surge", "mr": "Max rainfall", "hrs": "hours"}

    def g(v):
        return v if v not in (None, "") else "—"

    track_facts = ""
    if available:
        track_facts = (
            f"| {L['cur']} | {g(cs.get('location_label_bn') if bn else cs.get('location_label_en'))}; {g(cs.get('wind_speed_kmh'))} km/h; {g(cs.get('category_imd_en'))} |\n"
            f"| {L['path']} | {g(cs.get('direction_bn') if bn else cs.get('direction_en'))} |\n"
            f"| {L['land']} | {g(fs.get('landfall_place_bn') if bn else fs.get('landfall_place_en'))}; +{g(fs.get('lead_time_hours'))} {L['hrs']} |\n"
            f"| {L['mw']} | {g(fs.get('max_land_wind_kmh'))} km/h; {record_place(fs.get('max_wind_record'), lang)} |\n"
            f"| {L['ms']} | {g(fs.get('max_storm_surge_m'))} m; {record_place(fs.get('max_storm_surge_record'), lang)} |\n"
            f"| {L['mr']} | {g(fs.get('max_rainfall_mm'))} mm; {record_place(fs.get('max_rain_record'), lang)} |"
        )

    housing_share = "; ".join(
        f"{house_label(lang, k)}: {fmt(v, lang)}%" for k, v in (ctx.get("housing_percentages") or {}).items()
    ) or "—"
    members = ctx.get("member_count")
    members = members if members is not None else (1 if level == "union" else "—")

    facts = (
        f"| {L['metric']} | {L['value']} |\n|------|-----|\n"
        f"| {L['name']} | {cyclone_name or '—'} |\n"
        f"| {L['lvl']} | {level} |\n"
        f"| {L['area']} | {area_label(ctx, lang)} |\n"
        f"| {L['members']} | {members} |\n"
        f"| {L['risk']} | {g(ctx.get('risk'))} |\n"
        f"| {L['wind']} | {fmt(ctx.get('wind_speed_kmh'), lang)} km/h ({ctx.get('wind_class_label') or ''}) |\n"
        f"| {L['rain']} | {fmt(ctx.get('total_rainfall_mm'), lang)} mm |\n"
        f"| {L['surge']} | {fmt(ctx.get('storm_surge_m'), lang, 2)} m |\n"
        f"| {L['housing']} | {housing_share} |\n"
        f"| {L['dmg']} | {damage_lines} |\n"
        f"| {L['full']} | {full_damage_line} |\n"
        f"{track_facts}"
    )

    if bn:
        neap_section = f"\n\n## অগ্রাধিকার ১ — NEAP খাতভিত্তিক কার্যক্রম (স্প্রেডশিট; প্রধান ও কর্তৃত্বপূর্ণ উৎস)\n{neap['block']}" if neap.get("block") else ""
        rag_section = f"\n\n## অগ্রাধিকার ২ — NEAP নীতিমালা ও ওয়েব তথ্যসূত্র (সহায়ক)\n{rag_context}" if rag_context else ""
        return f"""আপনি বাংলাদেশের দুর্যোগ ব্যবস্থাপনা ও আবহাওয়া-ভিত্তিক আগাম কার্যক্রমে অভিজ্ঞ কর্মকর্তা। নিচের তথ্য ব্যবহার করে {area_label(ctx, lang)}-এর জন্য একটি Impact-Based Forecasting নির্দেশিকার বর্ণনামূলক অংশ তৈরি করুন। কোনো সংখ্যা, ফসল, স্থানীয় পেশা, অবকাঠামোর অবস্থা বা সময় উদ্ভাবন করবেন না। সম্পূর্ণ উত্তর বাংলা ভাষায় লিখুন।

এটি একটি **পূর্বাভাসভিত্তিক সম্ভাব্যতা**, নিশ্চিত ঘটনা নয়। তাই প্রভাব বর্ণনায় সর্বদা সম্ভাবনাসূচক ভাষা ব্যবহার করুন — "হতে পারে", "সম্ভাবনা রয়েছে", "আশঙ্কা রয়েছে", "ঝুঁকি রয়েছে"। কখনোই নিশ্চয়তাসূচক ভাষা ("হবে", "ঘটবে", "ধ্বংস হয়ে যাবে", "নিশ্চিতভাবে") ব্যবহার করবেন না।

### মূল তথ্য
{facts}

### তীব্রতা-সামঞ্জস্য
{wind_severity_guide(ctx.get('wind_speed_kmh'), lang)}

### প্রভাব-স্তর ও কার্যক্রমের মাত্রা (বাধ্যতামূলক ফিল্টার)
{impact_tier_guide(tier, lang)}
{neap_section}
{rag_section}

### বাধ্যতামূলক লেখার নিয়ম
0. **উৎসের অগ্রাধিকার ক্রম:** (ক) সবার আগে "অগ্রাধিকার ১ — NEAP খাতভিত্তিক কার্যক্রম" অংশ ব্যবহার করুন — এটিই মূল ও কর্তৃত্বপূর্ণ উৎস; প্রতিটি ব্লকের "টেমপ্লেট বিভাগ" লাইনে যে বিভাগ লেখা আছে, সেই কার্যক্রমগুলো ঠিক সেই বিভাগেই ব্যবহার করুন। (খ) এরপর "অগ্রাধিকার ২ — NEAP নীতিমালা ও ওয়েব তথ্যসূত্র" দিয়ে ঘাটতি পূরণ করুন। দুই উৎসে বিরোধ হলে অগ্রাধিকার ১ জিতবে। NEAP কার্যক্রমের ইংরেজি বাক্য হুবহু কপি করবেন না — এলাকার hazard মান অনুযায়ী বাংলায় পুনর্লিখন করুন।
0খ. **সময়-পর্যায়:** উপরের NEAP অংশে যে পর্যায় (RA প্রস্তুতিমূলক, না EA আগাম কার্যক্রম) দেওয়া আছে কেবল সেটিই প্রযোজ্য; অন্য পর্যায়ের কার্যক্রম লিখবেন না।
0খ২. **প্রভাব-মাত্রা (দ্বিতীয় বাধ্যতামূলক ছাঁকনি):** NEAP তালিকা কেবল ল্যান্ডফলের সময় অনুযায়ী সাজানো, ঘূর্ণিঝড়ের শক্তি অনুযায়ী নয়। তাই “প্রভাব-স্তর” অংশে যে মাত্রা দেওয়া আছে তার চেয়ে বেশি ব্যাঘাতমূলক কোনো কার্যক্রম লিখবেন না — সেখানে যেগুলো স্পষ্টভাবে নিষেধ করা আছে সেগুলো বাদ দিন, এমনকি NEAP তালিকায় থাকলেও। কম-প্রভাবের ঘূর্ণিঝড়ে আগাম ফসল কাটা, ব্যাপক সরিয়ে নেওয়া বা ঘের খালি করার পরামর্শ দেওয়া ভুল। উপযুক্ত হলে NEAP-এর কার্যক্রমকে ছোট মাত্রায় নামিয়ে লিখুন (যেমন “সব বাসিন্দাকে সরান” → “সবচেয়ে ঝুঁকিপূর্ণ কাঁচা ঘরের পরিবারগুলোকে সরান”)।
0গ. **majorImpact বনাম advisories — দুই ভিন্ন ধরনের বাক্য, কখনো মেশাবেন না।** majorImpact-এর প্রতিটি বুলেট শুধু **প্রভাব বর্ণনা করে**; তাতে কোনো নির্দেশ থাকবে না এবং স্তরভিত্তিক ভাগ হয় না। advisories-এর প্রতিটি বুলেট একটি **সরাসরি নির্দেশ**; একই সাতটি খাতে, প্রতিটি খাতে community ও institutional আলাদা।
0ঘ. **advisories-এর প্রতিটি খাতে community ও institutional আলাদা করে পূরণ করুন।** community = পরিবার ও সাধারণ মানুষ নিজে যা করবে। institutional = সরকারি দপ্তর ও প্রশাসন যা করবে। **কাউকে সরিয়ে নেওয়ার সিদ্ধান্ত বা আয়োজন সবসময় institutional।** কোনো স্তর খালি রাখবেন না; একই বাক্য দুই স্তরে লিখবেন না।
0ঙ. **কোনো বুলেটের শুরুতে খাতের নাম বা স্তরের নাম লিখবেন না।**
1. নির্ধারিত JSON স্কিমা হুবহু অনুসরণ করুন।
2. populationAndHouse-এ কাঁচা, আধা-পাকা ও পাকা ঘরের ফল আলাদাভাবে লিখুন।
3. raw JSON বা বন্ধনী ট্যাগ কখনো লিখবেন না।
4. কাঠামোগত উচ্চ-ক্ষতির কারণে অগ্রাধিকার সরিয়ে নেওয়ার ক্ষেত্রে শুধু এই তালিকা ব্যবহার করুন: {full_damage_line}।
5. agriculture অংশে শুধু ফসল/বীজতলা/ফসলি জমির ক্ষতি থাকবে।
6. **livestockFisheries:** গবাদিপশু ও হাঁস-মুরগি আগেভাগে নিরাপদ স্থানে সরানোর স্পষ্ট নির্দেশ দিন।
7. utilityService-এ বিদ্যুৎ, মোবাইল নেটওয়ার্ক, নিরাপদ পানি ও সড়ক আলাদা বুলেটে লিখুন।
8. majorImpact-এর প্রতিটি খাতে ২–৪টি বুলেট; advisories-এর প্রতিটি খাতে প্রতিটি স্তরে ২–৪টি বুলেট।
9. **পাকা ঘরের জন্য কোনো আগাম কাঠামোগত শক্তিশালীকরণ পরামর্শ দেবেন না।**
10. **healthDisease community অংশে লিখুন: অসুস্থরা আশ্রয়কেন্দ্রে মাস্ক পরবেন।**
11. **populationAndHouse community অংশে লিখুন: কাগজপত্র ওয়াটারপ্রুফ ব্যাগে নিয়ে যেতে হবে।**
12. কোনো তথ্যসূত্র নম্বর বা মার্কার লিখবেন না।"""

    neap_section_en = f"\n\n## Priority 1 — NEAP sector-wise actions (spreadsheets; primary, authoritative source)\n{neap['block']}" if neap.get("block") else ""
    rag_section_en = f"\n\n## Priority 2 — NEAP policy and web evidence (supporting)\n{rag_context}" if rag_context else ""
    return f"""You are an experienced Bangladesh disaster-management and impact-based forecasting officer. Using only the data below, write the narrative sections of an Impact-Based Forecasting guideline for {area_label(ctx, lang)}. Do not invent any number, crop, local occupation, infrastructure condition or time. **Write the entire response in clear, plain English** — no Bengali text anywhere in the output.

This is a **probabilistic forecast**, not a certain event. Always use likelihood wording — "may", "is likely to", "there is a risk of", "could". Never use certainty wording ("will happen", "will be destroyed", "definitely").

### Key data
{facts}

### Severity calibration
{wind_severity_guide(ctx.get('wind_speed_kmh'), lang)}

### Impact tier and action scale (mandatory filter)
{impact_tier_guide(tier, lang)}
{neap_section_en}
{rag_section_en}

### Mandatory writing rules
0. **Source priority order:** (a) Use "Priority 1 — NEAP sector-wise actions" first; it is the primary, authoritative source. Each block names the template section it belongs to on its "Template section:" line — put those actions in exactly that section. (b) Then fill remaining gaps from "Priority 2 — NEAP policy and web evidence". Where the two conflict, Priority 1 wins. Rewrite the NEAP actions in your own words, scaled to this area's hazard values — do not copy the source sentences verbatim.
0b. **Time phase:** only the phase shown in the NEAP section above (RA readiness, or EA early action) applies. Do not write actions belonging to the other phase.
0b2. **Impact scale (second mandatory filter):** the NEAP list is graded by time to landfall only, not by how strong the cyclone is. Never recommend an action more disruptive than the "Impact tier" section allows, and drop anything it explicitly rules out even when the NEAP list contains it.
0c. **majorImpact vs advisories — two different kinds of sentence, never mixed.** Every majorImpact bullet only DESCRIBES an impact in likelihood language, with no instruction, and is NOT split by level. Every advisories bullet is a direct INSTRUCTION, using the same seven sectors, each split into community and institutional.
0d. **In advisories, fill `community` and `institutional` separately for every sector.** Deciding, prioritising or organising anyone's evacuation is always institutional. Never leave a sector's level empty, and never repeat the same sentence in both levels.
0e. **Never prefix a bullet with a sector or level name.**
1. Follow the given JSON schema exactly. Every majorImpact bullet must make the causal chain explicit.
2. In populationAndHouse, report Kancha, Semi-pucca and Pucca separately.
3. Never emit raw JSON or bracketed tags.
4. For priority evacuation driven by structural damage, use only this list: {full_damage_line}.
5. Keep agriculture to crops, seedbeds and cropland only.
6. **livestockFisheries:** include a direct instruction to move livestock and poultry now to raised ground or a killa.
7. utilityService: separate bullets for electricity, mobile network, safe water, and road/transport.
8. Give 2–4 specific bullets in each majorImpact sector; 2–4 instructive bullets per sector per level in advisories.
9. **Never suggest advance structural strengthening for Pucca houses.**
10. **In advisories' healthDisease community entries, state that people who are unwell should wear a mask inside the shelter.**
11. **In advisories' populationAndHouse community entries, advise sealing documents in a waterproof bag and carrying them to the shelter.**
12. Do not write any reference number or citation marker."""


# ------------------------------------------------------------- text cleaning
_RAW_OPERATION_TAG = re.compile(r"\[\s*(?:প্রত্যাশিত কাঠামোগত ক্ষতি|সরিয়ে নেওয়া প্রয়োজন)[^\]]*\]\s*[।.]?", re.I)
_NON_CROP_TERMS = re.compile(r"গবাদি|পশু|হাঁস|মুরগি|মৎস্য|মাছ|চিংড়ি|নৌকা", re.I)
_CITATION_MARKER = re.compile(r"\s*\[\s*(?:তথ্যসূত্র|তথ্যসুত্র|রেফারেন্স|রেফ|ref\.?|source)?\s*[০-৯0-9]{1,3}(?:\s*[,、][^\]]*)?\s*\]", re.I)
_PUCCA_HOUSE = re.compile(r"পাকা\s*(?:ঘর|বাড়ি|বাসা)")
_STRENGTHEN_VERB = re.compile(r"বাঁধ|বেঁধে|শক্ত\s*কর|মজবুত|শক্তিশালী|দড়ি|জিআই\s*তার|খুঁটি\s*পুঁত|reinforc|strengthen|anchor|tie[-\s]?down", re.I)


def _tidy_spacing(text: str) -> str:
    text = re.sub(r"\s+([।,;:.!?])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _clean_text(value) -> str:
    if not isinstance(value, str):
        return ""
    return _tidy_spacing(_CITATION_MARKER.sub("", _RAW_OPERATION_TAG.sub("", value)))


def _suggests_pucca_strengthening(text: str) -> bool:
    if not _PUCCA_HOUSE.search(text):
        return False
    if re.search(r"কাঁচা|আধা[-\s]?পাকা", text):
        return False
    return bool(_STRENGTHEN_VERB.search(text))


_HIGH_IMPACT_ACTION = [
    re.compile(r"(?:ফসল|ধান|শস্য)[^।.]{0,40}(?:কেটে|কাটা|কাটুন|কর্তন)"),
    re.compile(r"(?:কেটে|কাটা|কাটুন|কর্তন)[^।.]{0,40}(?:ফসল|ধান|শস্য)"),
    re.compile(r"\bharvest\w*\b[^.]{0,60}\b(?:crops?|paddy|rice|grain)\b", re.I),
    re.compile(r"\b(?:crops?|paddy|rice|grain)\b[^.]{0,60}\bharvest", re.I),
    re.compile(r"(?:সবাইকে|সব\s*বাসিন্দা|সকলকে|পুরো\s*এলাকা)[^।.]{0,40}(?:সরিয়ে|সরান|আশ্রয়কেন্দ্রে)"),
    re.compile(r"(?:complete|full|mass|blanket)[^.]{0,25}\bevacuat", re.I),
    re.compile(r"evacuat[^.]{0,30}\b(?:everyone|all residents|entire)\b", re.I),
    re.compile(r"(?:ঘের|পুকুর)[^।.]{0,30}(?:খালি|মাছ\s*ধরে|জাল\s*দি)"),
    re.compile(r"\b(?:empty|net|harvest)\b[^.]{0,30}\b(?:fish|shrimp)\b[^.]{0,20}\b(?:enclosure|pond|farm)", re.I),
]


def _is_disproportionate_action(text: str, tier: str) -> bool:
    if tier not in ("minimal", "low"):
        return False
    return any(p.search(text) for p in _HIGH_IMPACT_ACTION)


def _compare_tokens(text: str) -> list[str]:
    return [t for t in re.split(r"\s+", re.sub(r"[।,;:.!?()\"'`—–\-/]", " ", text.lower())) if t]


def _similarity(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    shared = len(sa & sb)
    return (2 * shared) / (len(sa) + len(sb))


def _dedupe(items: list[str], threshold: float = 0.82) -> list[str]:
    kept: list[str] = []
    kept_tokens: list[list[str]] = []
    for item in items:
        tokens = _compare_tokens(item)
        if not tokens:
            continue
        if any(_similarity(prev, tokens) >= threshold for prev in kept_tokens):
            continue
        kept.append(item)
        kept_tokens.append(tokens)
    return kept


def _clean_array(value) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned = [_clean_text(v) for v in value]
    cleaned = [c for c in cleaned if c and not _suggests_pucca_strengthening(c)]
    return _dedupe(cleaned)


def _relocation_advisory(ctx: dict, lang: str) -> str:
    full_types = [house_label(lang, t) for t in full_damage_types(ctx)]
    return f"{', '.join(full_types)} {tr(lang, 'relocateFull')}" if full_types else tr(lang, "relocateNone")


# fallback_narrative is imported lazily to keep this module scannable.
from app.guidance.fallback import fallback_narrative  # noqa: E402


def _escape_re(text: str) -> str:
    return re.sub(r"([.*+?^${}()|\[\]\\])", r"\\\1", text)


_LEADING_LABEL = re.compile(
    r"^\s*(?:"
    + "|".join(
        _escape_re(x)
        for x in (
            *LEVEL_LABELS["bn"].values(),
            *LEVEL_LABELS["en"].values(),
            *CATEGORY_LABELS["bn"].values(),
            *CATEGORY_LABELS["en"].values(),
        )
    )
    + r")\s*[:：—–-]\s*",
    re.I,
)


def _strip_label(text: str) -> str:
    out = text.strip()
    for _ in range(3):
        if not _LEADING_LABEL.search(out):
            break
        out = _LEADING_LABEL.sub("", out).strip()
    return out


def _build_advisories(raw: dict | None, ctx: dict, fallback: dict, lang: str) -> dict:
    tier = impact_tier_for(ctx)
    out: dict = {}
    for level in LEVEL_KEYS:
        by_sector: dict = {}
        for category in IMPACT_CATEGORIES:
            entries = _clean_array((((raw or {}).get("advisories") or {}).get(level) or {}).get(category))
            if category == "agriculture":
                entries = [e for e in entries if not _NON_CROP_TERMS.search(e)]
            if not entries:
                entries = _clean_array(fallback["advisories"][level][category])
            items = list(entries)
            if level == "institutional" and category == "populationAndHouse" and full_damage_types(ctx):
                items.insert(0, _relocation_advisory(ctx, lang))
            by_sector[category] = _dedupe(
                [_strip_label(i) for i in items if not _is_disproportionate_action(i, tier)]
            )[:4]
        out[level] = by_sector
    return out


def _normalize_narrative(raw: dict, ctx: dict, lang: str) -> dict:
    fallback = fallback_narrative(ctx, lang, housing_damage_fact)
    fb = fallback["majorImpact"]
    major = (raw or {}).get("majorImpact") or {}

    def impact(key: str, minimum: int = 1, transform=lambda items: items) -> list[str]:
        cleaned = transform(_clean_array(major.get(key)))
        return cleaned if len(cleaned) >= minimum else transform(_clean_array(fb[key]))

    population = _dedupe(
        [housing_damage_fact(ctx, lang)]
        + [i for i in impact("populationAndHouse") if not re.search(r"সব ধরনের ঘর.*full damage|সকল প্রকার ঘর.*পূর্ণ", i, re.I)]
    )

    utility = impact("utilityService")
    if not any(re.search(r"বিদ্যুৎ|electric", i, re.I) for i in utility):
        utility.insert(0, fb["utilityService"][0])
    if not any(re.search(r"মোবাইল|network|BTS|টাওয়ার", i, re.I) for i in utility):
        utility.append(fb["utilityService"][1])

    return {
        "majorImpact": {
            "populationAndHouse": population[:4],
            "infrastructurePolder": impact("infrastructurePolder")[:4],
            "agriculture": impact("agriculture", 2, lambda items: [i for i in items if not _NON_CROP_TERMS.search(i)])[:4],
            "livestockFisheries": impact("livestockFisheries")[:4],
            "livelihood": impact("livelihood")[:4],
            "healthDisease": impact("healthDisease")[:4],
            "utilityService": _dedupe(utility)[:4],
        },
        "advisories": _build_advisories(raw, ctx, fallback, lang),
    }


def generate_guideline(
    *,
    cyclone_name: str,
    context: dict,
    cyclone_track: dict | None = None,
    lang: str = "bn",
    lead_time_hours=None,
    track_details: dict | None = None,
    data_quality_warnings: list[str] | None = None,
    rainfall_window_hours=None,
) -> dict:
    """Build one area's GuidelineDocument (LLM narrative + deterministic fields)."""
    ctx = context or {}
    lang = "en" if lang == "en" else "bn"
    cyc = cyclone_track or {}
    available = bool(cyc.get("available"))
    if lead_time_hours is None and available:
        lead_time_hours = (cyc.get("forecast_state") or {}).get("lead_time_hours")

    try:
        neap = neap_mod.build_neap_action_context(lead_time_hours, lang)
    except Exception as exc:  # noqa: BLE001
        print(f"[NEAP] action extraction failed: {exc}", flush=True)
        neap = {"phase": "both", "leadTimeHours": None, "rows": [], "inventory": "", "block": "", "itemCount": 0}

    try:
        rag_result = rag.retrieve(
            {
                "district": ctx.get("district"),
                "upazila": ctx.get("upazila") or ctx.get("name"),
                "windSpeed": ctx.get("wind_speed_kmh"),
                "rainfall": ctx.get("total_rainfall_mm"),
                "stormSurge": ctx.get("storm_surge_m"),
                "risk": ctx.get("risk"),
                "windClass": ctx.get("wind_class_label"),
            }
        )
        rag_context = rag_result["formattedContext"]
    except Exception as exc:  # noqa: BLE001
        print(f"[RAG] retrieval failed: {exc}", flush=True)
        rag_context = ""

    prompt = build_narrative_prompt(cyclone_name, ctx, rag_context, neap, lang, cyc)
    system_instruction = (
        "You are a Bangladesh disaster-management and meteorological officer. You write from a probabilistic forecast, not a certain event: always express impacts as likelihood, never as certainty. Ground every section in the NEAP sector-wise actions given as Priority 1 first, then the Priority 2 policy and web evidence, and use only the landfall phase (RA or EA) shown there. Major Impact only DESCRIBES what the cyclone may do (no level split, no instructions); advisories only ADVISES what to do (an instruction in every bullet), split into community and institutional. Never restate a majorImpact sentence as an advisory or vice versa, and never prefix a bullet with a sector or level name. Do not invent numeric data; keep damage separate by house type; never suggest advance structural strengthening for Pucca houses; write no reference numbers or citation markers. Respond in JSON, entirely in clear, plain English — no Bengali text anywhere."
        if lang == "en"
        else "আপনি বাংলাদেশের দুর্যোগ ব্যবস্থাপনা ও আবহাওয়া কর্মকর্তা। আপনি একটি সম্ভাব্য পূর্বাভাসের ভিত্তিতে লেখেন, নিশ্চিত ঘটনার নয়: প্রতিটি প্রভাব সর্বদা সম্ভাবনাসূচক ভাষায় লিখুন। প্রথমে NEAP খাতভিত্তিক কার্যক্রম (অগ্রাধিকার ১) ব্যবহার করুন, এরপর অগ্রাধিকার ২; সেখানে দেওয়া ল্যান্ডফল পর্যায় ছাড়া অন্য পর্যায়ের কার্যক্রম লিখবেন না। majorImpact শুধু বর্ণনা করে (স্তরবিহীন, নির্দেশ নয়); advisories শুধু নির্দেশ দেয়, community ও institutional-এ ভাগ। কোনো বুলেটের শুরুতে খাত/স্তরের নাম লিখবেন না। সংখ্যাগত তথ্য উদ্ভাবন করবেন না; ঘরের ধরনভিত্তিক ক্ষতি আলাদা রাখুন; পাকা ঘরের জন্য আগাম শক্তিশালীকরণ নয়; তথ্যসূত্র চিহ্ন নয়। আনুষ্ঠানিক বাংলায় JSON উত্তর দিন।"
    )

    token_budgets = [8192, 12288]
    deadline = time.time() + 120
    narrative: dict | None = None
    for max_tokens in token_budgets:
        if time.time() >= deadline:
            break
        try:
            payload = gemini.generate_content(
                prompt,
                system_instruction=system_instruction,
                response_schema=GEMINI_NARRATIVE_SCHEMA,
                max_output_tokens=max_tokens,
                timeout_s=55,
                deadline=deadline,
            )
            narrative = json.loads(gemini.extract_text(payload))
            break
        except Exception as exc:  # noqa: BLE001
            print(f"[guideline] Gemini attempt failed (max_tokens={max_tokens}): {exc}", flush=True)

    if not narrative:
        narrative = fallback_narrative(ctx, lang, housing_damage_fact)

    document_narrative = _normalize_narrative(narrative, ctx, lang)
    deterministic = build_deterministic_fields(cyclone_name, ctx, track_details or {}, lang, cyc)
    warnings = [w for w in (data_quality_warnings or []) if isinstance(w, str) and w.strip()]

    return {
        "cycloneName": cyclone_name or ("Unknown" if lang == "en" else "অজানা"),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "analysisLevel": analysis_level(ctx),
        "selectedArea": area_label(ctx, lang),
        "levelLabels": LEVEL_LABELS[lang],
        "rainfallWindowHours": rainfall_window_hours if _is_num(rainfall_window_hours) else None,
        "trackMapUrl": cyc.get("track_map_url"),
        "dataQualityWarnings": warnings,
        **deterministic,
        **document_narrative,
    }
