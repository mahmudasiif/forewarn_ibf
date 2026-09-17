"""Preparedness request/response models — the API contract for this module."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

RunStatus = Literal["queued", "running", "succeeded", "failed"]
DamageModel = Literal["ccm", "safir"]


class ArtifactInfo(BaseModel):
    label: str
    name: str
    content_type: str
    size: int


class RunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cyclone_name: str
    status: RunStatus
    damage_model: str
    llm_polished: bool
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class RunDetail(RunSummary):
    polished: bool
    input_files: dict[str, Any] = {}
    summary: dict[str, Any] | None = None
    guideline_markdown: str | None = None
    artifacts: list[ArtifactInfo] | None = None
    error: str | None = None


# --- interactive (Phase 2) request bodies ---


class GuidelineBody(BaseModel):
    #: the selected area's analysis context (from GET /runs/{id}/contexts)
    context: dict[str, Any]
    lang: Literal["bn", "en"] = "bn"


class AreaMapBody(BaseModel):
    level: Literal["union", "upazila", "district"]
    metric: Literal["wind", "rainfall", "surge", "risk"]
    district: str = ""
    upazila: str = ""
    union: str = ""
    geo_code: str = ""
    lang: Literal["bn", "en"] = "bn"


class DocxBody(BaseModel):
    document: dict[str, Any]
    track_map_b64: str | None = None


class SaveGuidelineBody(BaseModel):
    document: dict[str, Any]
    area_name: str = "guideline"
