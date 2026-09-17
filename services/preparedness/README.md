# Preparedness Guidance model service

Module 3 — Cyclone Preparedness Guidance. Wraps the IWFM/BUET hackathon impact
model (vendored in `app/model/pipeline.py`) behind the portal's model-service
HTTP contract. The core API never imports this package; it talks HTTP only.

## Endpoints

| Method | Path       | Purpose                                             |
|--------|------------|-----------------------------------------------------|
| GET    | `/health`  | liveness + GIS-cache readiness (`gis_loaded`)       |
| GET    | `/info`    | name, version, readiness, input/output JSON schema  |
| POST   | `/predict` | run the impact pipeline for one forecast (sync)     |

`/predict` is **synchronous and path-based**: the request carries file paths on
the `prep-runs` volume shared with the Celery worker, which is the async layer.
The pipeline warm-loads the GIS boundaries once at startup, so the first
`/health` returns `"status":"loading"` until the cache is ready (~1–3 min).

## Static assets (not committed — 206 MB)

The pipeline reads BBS-2022 GIS boundaries, housing/demographic CSV, structure
damage workbook and NEAP sources from `assets/` (mounted read-only in compose,
git-ignored). Populate it from the handover before first run:

```bash
bash scripts/setup-preparedness-assets.sh
```

Expected layout under `assets/`:

```
BD Union BBS 2022/BD_Union_BBS_2022.shp (+ .dbf .shx .prj ...)
BD Upazila BBS 2022/BD_Upazila_BBS_2022.shp ...
BD District BBS 2022/BD_District_BBS_2022.shp ...
BD_Union_BBS21.shp ...            # legacy union boundaries (fallback)
union_bbs.csv                     # housing + demographic columns
StructureDamageData.xlsx
Neap_RAG.docx                     # used by Phase 2 (advanced guidance)
NEAP sector-wise actions spreadsheet-selected/*.xlsx   # Phase 2
```

## Guidance & keys

The base Bengali guideline is produced by the pipeline itself. LLM polish is
attempted only when `GOOGLE_API_KEYS` is set; with no key the run still succeeds
and returns the unpolished base guideline. The advanced NEAP + RAG + structured
guidance is Phase 2 (see the project plan).

## Note on `damage_model`

`damage_model` accepts `"ccm"` (default) or `"safir"` — these are damage-curve
names *inside this model* and are unrelated to the portal's separate CCM module.
