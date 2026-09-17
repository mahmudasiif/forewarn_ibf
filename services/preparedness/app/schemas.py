"""The contract this service exposes.

The impact pipeline is filesystem-based (it reads the forecast file and writes a
folder of maps/spreadsheets), so `/predict` takes and returns *paths* on the
volume shared with the Celery worker — not inline blobs. This mirrors the
handover's own `/process` body.
"""
from typing import Any

from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    #: wind-speed forecast: .nc / .csv / .xlsx / .xls
    input: str
    #: directory the pipeline writes all artifacts into
    output: str
    #: path to write the manifest JSON
    manifest: str
    #: optional independent hazard inputs
    rainfall: str | None = None
    storm_surge: str | None = None
    #: internal damage-curve model — "ccm" (default) or "safir". NOTE: this
    #: "ccm" is a damage curve inside this model, unrelated to the portal's CCM
    #: module.
    damage_model: str = "ccm"
    cyclone_name: str | None = None
    #: attempt LLM polish of the guideline (only honoured when a key is set)
    polished: bool = True


class PredictResponse(BaseModel):
    status: str = "ok"
    #: whether an LLM key was available and polish was attempted this run
    llm_polished: bool = False


class InfoResponse(BaseModel):
    name: str
    version: str
    ready: bool
    llm_available: bool
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


class AreaMapRequest(BaseModel):
    level: str                 # union | upazila | district
    metric: str                # wind | rainfall | surge | risk
    output: str                # PNG path to write (on the shared volume)
    metrics_path: str          # area_metrics.json produced by /predict
    district: str = ""
    upazila: str = ""
    union: str = ""
    geo_code: str = ""
    lang: str = "bn"


class GuidelineRequest(BaseModel):
    cyclone_name: str = ""
    context: dict[str, Any]
    cyclone_track: dict[str, Any] | None = None
    lang: str = "bn"
    lead_time_hours: float | None = None
    track_details: dict[str, Any] | None = None
    data_quality_warnings: list[str] | None = None
    rainfall_window_hours: float | None = None


class GuidelineDocxRequest(BaseModel):
    document: dict[str, Any]
    #: optional base64-encoded track-map JPEG to embed
    track_map_b64: str | None = None
