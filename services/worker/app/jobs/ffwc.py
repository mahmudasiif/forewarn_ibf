"""Pull FFWC water-level data from the public legacy site and write a daily CSV.

Source (no auth, public):
  http://old.ffwc.gov.bd/ffwc_charts/waterlevelfcast.php

The page is an HTML table:
  River Name | Station | Danger Level (mMSL) | <N observed dates> | <M forecast dates>
The observed/forecast split is authoritative from the category header row's
``colspan`` (id cols / WL-Observe / WL-Forecast), not guessed from dates.

Output: a tidy long-format CSV, one row per (station, reading date):
  pulled_at, source, river, station, danger_level_mmsl,
  reading_date, reading_time, reading_type, water_level_mmsl

Everything here is defensive: a bad fetch or a layout change must never crash
the worker — the task logs and returns a status dict instead.
"""
from __future__ import annotations

import csv
import html as _html
import logging
import os
import re
import urllib.request
from datetime import date, datetime, timezone, timedelta

from app.celery_app import celery_app

log = logging.getLogger(__name__)

FCAST_URL = os.getenv(
    "FFWC_FCAST_URL", "http://old.ffwc.gov.bd/ffwc_charts/waterlevelfcast.php"
)
CSV_DIR = os.getenv("FFWC_CSV_DIR", "/data/ffwc")
# Asia/Dhaka is UTC+6, no DST — fine to hardcode for a "pull date" stamp.
DHAKA = timezone(timedelta(hours=6))

# Only the station(s) DFRM needs are written to the CSV. DFRM is driven by the
# Jamuna at Bahadurabad; add ("Dharla", "Kurigram") here if the Dharla/Kurigram
# side is ever wired in too.
TARGET_STATIONS = {("Jamuna", "Bahadurabad")}

CSV_HEADER = [
    "pulled_at",
    "source",
    "river",
    "station",
    "danger_level_mmsl",
    "reading_date",
    "reading_time",
    "reading_type",
    "water_level_mmsl",
]


# --------------------------------------------------------------------------- #
# Fetch + parse
# --------------------------------------------------------------------------- #
def _fetch(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "forewarn-ibf/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _cell_text(raw: str) -> str:
    return _html.unescape(re.sub(r"<[^>]+>", "", raw)).strip()


def _cells_with_span(tr: str) -> list[tuple[str, int]]:
    """Return [(text, colspan)] for one <tr>."""
    out = []
    for attrs, body in re.findall(r"<t[dh]([^>]*)>(.*?)</t[dh]>", tr, re.S | re.I):
        m = re.search(r"colspan\s*=\s*['\"]?(\d+)", attrs, re.I)
        out.append((_cell_text(body), int(m.group(1)) if m else 1))
    return out


def _resolve_year(dd: int, mm: int, pull: date) -> int:
    """DD-MM headers have no year; pick the year that lands nearest the pull date."""
    best, best_gap = pull.year, None
    for yr in (pull.year - 1, pull.year, pull.year + 1):
        try:
            gap = abs((date(yr, mm, dd) - pull).days)
        except ValueError:
            continue
        if best_gap is None or gap < best_gap:
            best, best_gap = yr, gap
    return best


def parse_forecast(page: str, pull: date) -> list[dict]:
    """Parse the forecast page into per-station records.

    Each record: {river, station, danger_level, readings: [{date, time, type, wl}]}
    """
    trs = re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S | re.I)
    if len(trs) < 3:
        raise ValueError("unexpected FFWC layout: fewer than 3 rows")

    # Row 0: category header with colspans -> [id_cols, n_observed, n_forecast]
    cat = _cells_with_span(trs[0])
    spans = [span for _, span in cat]
    if len(spans) < 3:
        raise ValueError(f"unexpected category header: {cat}")
    id_cols, n_obs, n_fcast = spans[0], spans[1], spans[2]

    # Row 1: column headers -> dates start after the id columns
    cols = [t for t, _ in _cells_with_span(trs[1])]
    date_labels = cols[id_cols:]
    # Row 2: times (all "06:00 AM" typically); align to the dated columns
    times = [t for t, _ in _cells_with_span(trs[2])]

    # Resolve each dated column to (date, time, type)
    col_meta = []
    for i, label in enumerate(date_labels):
        m = re.match(r"(\d{1,2})[-/](\d{1,2})", label)
        if not m:
            col_meta.append(None)
            continue
        dd, mm = int(m.group(1)), int(m.group(2))
        yr = _resolve_year(dd, mm, pull)
        try:
            rdate = date(yr, mm, dd).isoformat()
        except ValueError:
            col_meta.append(None)
            continue
        rtime = times[i].strip() if i < len(times) else ""
        rtype = "observed" if i < n_obs else "forecast"
        col_meta.append({"date": rdate, "time": rtime, "type": rtype})

    n_value_cols = n_obs + n_fcast
    records: list[dict] = []
    for tr in trs[2:]:
        cells = [t for t, _ in _cells_with_span(tr)]
        if len(cells) != id_cols + n_value_cols:
            continue
        river, station, dl = cells[0], cells[1], cells[2]
        if not re.match(r"^-?\d+(\.\d+)?$", dl):  # danger level must be numeric
            continue
        readings = []
        for i in range(n_value_cols):
            meta = col_meta[i] if i < len(col_meta) else None
            val = cells[id_cols + i].strip()
            if meta is None or val in ("", "-", "NA", "N/A"):
                continue
            if not re.match(r"^-?\d+(\.\d+)?$", val):
                continue
            readings.append({**meta, "wl": val})
        records.append(
            {"river": river, "station": station, "danger_level": dl, "readings": readings}
        )
    if not records:
        raise ValueError("parsed FFWC page but found no station rows")
    return records


# --------------------------------------------------------------------------- #
# CSV
# --------------------------------------------------------------------------- #
def to_rows(records: list[dict], pulled_at: str) -> list[list]:
    rows = []
    for rec in records:
        for r in rec["readings"]:
            rows.append(
                [
                    pulled_at,
                    FCAST_URL,
                    rec["river"],
                    rec["station"],
                    rec["danger_level"],
                    r["date"],
                    r["time"],
                    r["type"],
                    r["wl"],
                ]
            )
    return rows


def write_csv(path: str, rows: list[list]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_HEADER)
        w.writerows(rows)


def _upload_best_effort(path: str, key: str) -> str | None:
    """Upload to MinIO if reachable; never fail the task on storage errors."""
    try:
        from app.storage import put_file

        return put_file(key, path, content_type="text/csv")
    except Exception as exc:  # noqa: BLE001 - storage is optional here
        log.warning("FFWC CSV MinIO upload skipped: %s", exc)
        return None


# --------------------------------------------------------------------------- #
# Task
# --------------------------------------------------------------------------- #
@celery_app.task(name="app.jobs.ffwc.pull_ffwc")
def pull_ffwc() -> dict:
    """Fetch FFWC forecast, write today's CSV locally and to MinIO. Best-effort."""
    now = datetime.now(DHAKA)
    pull_date = now.date()
    pulled_at = now.isoformat(timespec="seconds")
    try:
        page = _fetch(FCAST_URL)
        all_records = parse_forecast(page, pull_date)
    except Exception as exc:  # noqa: BLE001 - must not crash the worker
        log.exception("FFWC pull failed")
        return {"status": "error", "error": str(exc), "pulled_at": pulled_at}

    # Keep only the station(s) DFRM needs (Bahadurabad).
    records = [r for r in all_records if (r["river"], r["station"]) in TARGET_STATIONS]
    if not records:
        log.error("FFWC pull: none of %s found among %d stations",
                  TARGET_STATIONS, len(all_records))
        return {"status": "error", "error": "target station not found",
                "pulled_at": pulled_at, "stations_seen": len(all_records)}

    rows = to_rows(records, pulled_at)
    fname = f"ffwc_{pull_date.isoformat()}.csv"
    path = os.path.join(CSV_DIR, fname)
    write_csv(path, rows)
    key = _upload_best_effort(path, f"ffwc/{fname}")

    # Fresh data has arrived -> kick off the DFRM 5-day forecast automation,
    # handing it the Bahadurabad record we already parsed (no re-fetch). Lazy
    # import to avoid a circular import; best-effort so a trigger failure never
    # fails the pull itself.
    dfrm_task_id = None
    try:
        from app.jobs.dfrm_forecast import run_dfrm_forecast

        dfrm_task_id = run_dfrm_forecast.delay(records[0]).id
    except Exception as exc:  # noqa: BLE001 - trigger failure must not fail the pull
        log.warning("Could not enqueue DFRM forecast: %s", exc)

    summary = [
        {"station": r["station"], "danger_level": r["danger_level"],
         "forecast": [x["wl"] for x in r["readings"] if x["type"] == "forecast"]}
        for r in records
    ]
    return {
        "status": "ok",
        "pulled_at": pulled_at,
        "csv_path": path,
        "minio_key": key,
        "stations": len(records),
        "rows": len(rows),
        "data": summary,
        "dfrm_task_id": dfrm_task_id,
    }


if __name__ == "__main__":  # standalone test: python -m app.jobs.ffwc
    import json

    print(json.dumps(pull_ffwc(), indent=2, default=str))
