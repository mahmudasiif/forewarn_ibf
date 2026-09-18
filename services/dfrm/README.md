# DFRM — Dynamic Flood Risk Model (Module 7)

A stateless model micro-service that ports the DFRM v5.2 desktop tool
(*Md. Manjurul Husain Shourov*) to the FOREWARN portal contract. No PyQt, no
files to upload: a water level at a river station drives a design-hydrograph
lookup that indexes pre-computed flood layers for the Jamuna/Dharla system.

## Endpoints

| Method | Path              | Purpose                                                        |
|--------|-------------------|----------------------------------------------------------------|
| GET    | `/health`         | liveness                                                       |
| GET    | `/info`           | name, version, readiness, input/output schema                  |
| POST   | `/predict`        | one-shot map or warning (`kind: "map" \| "warning"`)           |
| POST   | `/predict/async`  | queue the same work → `{job_id}`                               |
| GET    | `/jobs/{id}`      | job status + result                                            |
| GET    | `/areas`          | District → Upazilla → Union → Village picker + stations/limbs  |
| POST   | `/map`            | a graded layer (Inundation/Hazard/Risk/Vulnerability) as GeoJSON |
| POST   | `/warning`        | per-area flood warning table (risk level, depth, duration, …)  |

## How it works

1. A **water level** (absolute, or "above danger level") is chosen at the
   station gauging the selected area — Bahadurabad (Jamuna, DL 19.05 m) or
   Kurigram (Dharla, DL 26.5 m).
2. The rising/falling **limb** + water level pick the closest day on the design
   hydrograph (`WL_Hydrograph.xls`); that day's column (`day_N`) indexes every
   layer.
3. **Map** reads `Union_<layer>.shp`, repairs invalid polygons, min-max
   normalises the graded layers to 0–100, filters to the admin boundary, and
   returns a GeoJSON `FeatureCollection` plus clipped river-corridor/active-channel
   base layers and `context` upazila/district outlines (dissolved from the same
   union geometry, so they trace the choropleth exactly).
4. **Warning** joins `Warning.xlsx` + the `WD_*/Du_*` class sheets for the day
   and returns the per-area warning table.
5. `return_period()` is the GEV fit at Bahadurabad.

## Reference data

`assets/DFRM_Database/` (shapefiles + spreadsheets, ~20 MB) is **git-ignored**
and mounted read-only at `/app/assets`. Set `DFRM_ASSETS_DIR` to point elsewhere
for local runs.

Generate/refresh the assets — copies the DFRM v5.2 database into place:

```bash
python3 scripts/dfrm_setup_assets.py
# override the source if it lives elsewhere:
#   DFRM_SRC="/path/DFRM v5.2 - For Share" python3 scripts/dfrm_setup_assets.py
```

Admin context outlines (upazila / district) are derived at runtime by dissolving
the union geometry — no separate boundary files are needed.
