"""DFRM automation — turn the FFWC Bahadurabad forecast into a 5-day outlook.

Current-state policy: each forecast day is classified on its own level and its
own *local* trend — the limb is "Flood Increasing" when that day's water level
is >= the previous day's (the latest observed level anchors day 1), else
"Flood Decreasing". Phase is the level relative to the danger level.

Staged build:
  * Stage 1 (this file, now): pure classifier + a task that logs the 5-day set.
    No DB, no DFRM service calls, no area scope yet.
  * Later stages add: DFRM /map + /warning per day, persistence, an API, and the
    web "5-Day Forecast" tab. See the architecture in the project notes.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import urllib.request
from datetime import date, datetime

from sqlalchemy import create_engine, text

from app import storage
from app.celery_app import celery_app
from app.jobs.ffwc import DHAKA, FCAST_URL, TARGET_STATIONS, _fetch, parse_forecast

log = logging.getLogger(__name__)

#: Water level within this margin (m) below the danger level counts as "Warning".
#: FFWC has a distinct Warning Level we don't ingest; this is a stand-in.
WARNING_MARGIN_M = 0.5

#: Internal DFRM model service (same network as the API's DFRM client).
DFRM_URL = os.getenv("DFRM_SERVICE_URL", "http://dfrm:8000")
#: Map layers generated per day. Inundation (flood extent) is the default view;
#: the 5-day tab lets the user switch between all of them.
FORECAST_LAYERS = [
    x.strip()
    for x in os.getenv(
        "DFRM_FORECAST_LAYERS", "Inundation,Hazard,Risk,Vulnerability"
    ).split(",")
    if x.strip()
]
#: Areas the auto-run covers. District level is entirely Jamuna-driven (Bahadurabad),
#: so both districts are correctly driven by the single Bahadurabad feed.
FORECAST_LEVEL = "District"
TARGET_AREAS = [("Dist_01", "Jamalpur"), ("Dist_02", "Kurigram")]


def phase_for(wl: float, danger: float) -> str:
    if wl >= danger:
        return "Flood"
    if wl >= danger - WARNING_MARGIN_M:
        return "Warning"
    return "Normal"


def classify_forecast(record: dict) -> list[dict]:
    """Current-state classification: Today (latest observed) + each forecast day.

    ``record`` is a parse_forecast() row: {river, station, danger_level,
    readings: [{date, time, type(observed|forecast), wl}]}.
    Returns entries in chronological order: day_index 0 = Today (most recent
    observed level), then day_index 1..N for the FFWC forecast days.
    """
    danger = float(record["danger_level"])
    observed = sorted(
        (r for r in record["readings"] if r["type"] == "observed"),
        key=lambda r: r["date"],
    )
    forecast = sorted(
        (r for r in record["readings"] if r["type"] == "forecast"),
        key=lambda r: r["date"],
    )

    days: list[dict] = []

    # day 0 = Today: the most recent observed level; limb vs the prior observed.
    if observed:
        today = observed[-1]
        today_wl = float(today["wl"])
        prev_obs = float(observed[-2]["wl"]) if len(observed) >= 2 else None
        today_limb = (
            "Flood Increasing" if prev_obs is None or today_wl >= prev_obs else "Flood Decreasing"
        )
        days.append(
            {
                "day_index": 0,
                "date": today["date"],
                "water_level": today_wl,
                "prev_water_level": prev_obs,
                "limb": today_limb,
                "phase": phase_for(today_wl, danger),
            }
        )

    # Forecast days: anchor day 1 on the most recent observed level.
    prev = float(observed[-1]["wl"]) if observed else (
        float(forecast[0]["wl"]) if forecast else None
    )
    for i, r in enumerate(forecast, start=1):
        wl = float(r["wl"])
        if prev is None or wl >= prev:
            limb = "Flood Increasing"
        else:
            limb = "Flood Decreasing"
        days.append(
            {
                "day_index": i,
                "date": r["date"],
                "water_level": wl,
                "prev_water_level": prev,
                "limb": limb,
                "phase": phase_for(wl, danger),
            }
        )
        prev = wl
    return days


def _dfrm_post(path: str, body: dict, timeout: int = 180) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        DFRM_URL + path, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def _upload_json(obj: dict, key: str) -> str:
    """Write a JSON blob to a temp file and upload it to MinIO under ``key``."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(obj, fh)
        tmp = fh.name
    try:
        storage.put_file(key, tmp, content_type="application/json")
    finally:
        os.unlink(tmp)
    return key


def build_day_area_layer_row(
    day: dict, area_id: str, area_name: str, layer: str, run_date: date
) -> dict:
    """Call DFRM /map for one day+area+layer, upload the map JSON, return a row dict.

    Defensive: a failed call yields a row with status='error' rather than raising,
    so one bad day/area/layer never sinks the whole set.
    """
    row = {
        "day_index": day["day_index"],
        "forecast_date": day["date"],
        "water_level": day["water_level"],
        "prev_water_level": day["prev_water_level"],
        "limb": day["limb"],
        "phase": day["phase"],
        "area_id": area_id,
        "area_name": area_name,
        "layer": layer,
        "river": "Jamuna",  # District level always routes to Jamuna/Bahadurabad
        "station": "Bahadurabad (Jamuna)",
        "hydrograph_day": None,
        "return_period": None,
        "feature_count": None,
        "metric_unit": None,
        "metric_min": None,
        "metric_max": None,
        "map_key": None,
        "status": "ok",
        "error": None,
    }
    body = {
        "level": FORECAST_LEVEL,
        "area_id": area_id,
        "layer": layer,
        "water_level": day["water_level"],
        "wl_kind": "WL",
        "limb": day["limb"],
    }
    try:
        resp = _dfrm_post("/map", body)
        key = (
            f"dfrm/forecast/{run_date.isoformat()}/"
            f"day{day['day_index']}_{area_id}_{layer}.json"
        )
        _upload_json(resp, key)
        row.update(
            station=resp.get("station") or row["station"],
            hydrograph_day=resp.get("day"),
            return_period=resp.get("return_period"),
            feature_count=resp.get("feature_count"),
            metric_unit=resp.get("metric_unit"),
            metric_min=resp.get("metric_min"),
            metric_max=resp.get("metric_max"),
            map_key=key,
        )
    except Exception as exc:  # noqa: BLE001 - one call failing must not stop the rest
        log.warning(
            "DFRM /map failed day=%s area=%s layer=%s: %s",
            day["date"], area_id, layer, exc,
        )
        row.update(status="error", error=str(exc))
    return row


def _engine():
    url = os.getenv("DATABASE_URL", "postgresql+asyncpg://forewarn:change_me@db:5432/forewarn")
    return create_engine(url.replace("+asyncpg", "+psycopg2"), pool_pre_ping=True)


def persist_set(set_meta: dict, rows: list[dict]) -> int:
    """Replace any existing set for this run_date, then insert the set + day rows."""
    eng = _engine()
    try:
        with eng.begin() as conn:
            conn.execute(
                text("DELETE FROM dfrm.forecast_sets WHERE run_date = :run_date"),
                {"run_date": set_meta["run_date"]},
            )
            set_id = conn.execute(
                text(
                    """
                    INSERT INTO dfrm.forecast_sets
                      (run_date, source, station, danger_level, observed_wl, layer, level, pulled_at)
                    VALUES
                      (:run_date, :source, :station, :danger_level, :observed_wl, :layer, :level, :pulled_at)
                    RETURNING id
                    """
                ),
                set_meta,
            ).scalar_one()
            for r in rows:
                conn.execute(
                    text(
                        """
                        INSERT INTO dfrm.forecast_days
                          (set_id, day_index, forecast_date, water_level, prev_water_level, limb, phase,
                           area_id, area_name, layer, river, station, hydrograph_day, return_period, feature_count,
                           metric_unit, metric_min, metric_max, map_key, status, error)
                        VALUES
                          (:set_id, :day_index, :forecast_date, :water_level, :prev_water_level, :limb, :phase,
                           :area_id, :area_name, :layer, :river, :station, :hydrograph_day, :return_period, :feature_count,
                           :metric_unit, :metric_min, :metric_max, :map_key, :status, :error)
                        """
                    ),
                    {**r, "set_id": set_id},
                )
        return set_id
    finally:
        eng.dispose()


def latest_bahadurabad() -> dict | None:
    """Fetch + parse the FFWC page and return the Bahadurabad record (or None)."""
    page = _fetch(FCAST_URL)
    for r in parse_forecast(page, date.today()):
        if (r["river"], r["station"]) in TARGET_STATIONS:
            return r
    return None


@celery_app.task(name="app.jobs.dfrm_forecast.run_dfrm_forecast")
def run_dfrm_forecast(record: dict | None = None) -> dict:
    """Stage 1: classify the latest FFWC Bahadurabad forecast into a 5-day set.

    ``record`` may be passed in (e.g. chained from pull_ffwc) to avoid re-fetching;
    if omitted, the task fetches it itself.
    """
    now = datetime.now(DHAKA)
    run_date = now.date()
    if record is None:
        record = latest_bahadurabad()
    if not record:
        log.error("DFRM forecast: Bahadurabad record not found")
        return {"status": "error", "error": "Bahadurabad not found"}

    days = classify_forecast(record)
    observed = sorted(
        (r for r in record["readings"] if r["type"] == "observed"), key=lambda r: r["date"]
    )
    observed_wl = float(observed[-1]["wl"]) if observed else None

    # Run DFRM /map per day x area x layer, upload each map JSON, collect DB rows.
    rows: list[dict] = []
    for d in days:
        for area_id, area_name in TARGET_AREAS:
            for layer in FORECAST_LAYERS:
                rows.append(build_day_area_layer_row(d, area_id, area_name, layer, run_date))

    set_meta = {
        "run_date": run_date,
        "source": "FFWC/Bahadurabad",
        "station": record["station"],
        "danger_level": float(record["danger_level"]),
        "observed_wl": observed_wl,
        "layer": FORECAST_LAYERS[0],  # default layer the UI opens on
        "level": FORECAST_LEVEL,
        "pulled_at": now,
    }
    set_id = persist_set(set_meta, rows)
    ok = sum(1 for r in rows if r["status"] == "ok")
    log.info(
        "DFRM forecast persisted — set=%s run_date=%s days=%s layers=%s rows=%s ok=%s",
        set_id, run_date, len(days), len(FORECAST_LAYERS), len(rows), ok,
    )
    return {
        "status": "ok",
        "set_id": set_id,
        "run_date": run_date.isoformat(),
        "layers": FORECAST_LAYERS,
        "level": FORECAST_LEVEL,
        "days": len(days),
        "rows": len(rows),
        "ok": ok,
    }


if __name__ == "__main__":  # standalone test: python -m app.jobs.dfrm_forecast
    import json

    print(json.dumps(run_dfrm_forecast(), indent=2, default=str))
