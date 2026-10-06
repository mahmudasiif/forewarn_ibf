# CCM model service

The real Cyclone Classifier Model (v2.9.3), ported from the CCM 2.9 (with
Rain) desktop tool written at BUET by Md. Manjurul Husain Shourov. The
calculation in `app/model/engine.py` is a faithful port of that tool's
`CCM_Update_Database.py`; the PyQt interface and the matplotlib preview map
were dropped, since the portal supplies its own UI and Leaflet map.

## What it does

Given one cyclone's simulation output — water-depth, wind-speed and rainfall
grids plus a track shapefile, produced upstream by a storm-surge model and
*not* by this service — it returns one row per coastal union with surge
height, wind speed, thrust force, rainfall, polder/structure/agriculture
damage condition, flooded area, house damage, affected people and houses,
and the Hazard / Vulnerability / Risk percentages.

## Endpoints

| Method | Path     | Purpose                                      |
|--------|----------|----------------------------------------------|
| GET    | /health  | liveness                                     |
| GET    | /info    | version, readiness, required files, columns  |
| POST   | /runs    | run the model over one cyclone (multipart)   |

`/runs` is synchronous and slow (minutes — millions of grid points joined
against 1,585 union polygons). The portal API owns run bookkeeping and calls
it with a long timeout; this service stores nothing.

## Reference data

Mounted read-only at `CCM_DATA_DIR` (default `/data/ccm/CycloneDataBase`) —
the same folder `scripts/import_ccm.py` imports from. It is loaded once at
startup. Note the engine joins against the model's **own** boundary layers
(`CCM_Unions_wgs84`, `CCM_Unions_without_River_wgs84`), not the
`CCM_Unions_BBS21` display layer: the housing and polder tables are keyed to
the original `Union_Geo` codes.
