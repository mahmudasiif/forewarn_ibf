# FOREWARN IBF Portal — Project Map

Monorepo. Don't re-explore the tree — use this map first.

## Structure
- `apps/web/` — React SPA frontend
- `apps/api/` — FastAPI backend (Gunicorn/Uvicorn)
- `services/dfrm/` — Dynamic Flood Risk Model service (internal only, port 8000, called via `DFRM_SERVICE_URL`)
- `services/preparedness/` — Cyclone Advisory/Guidance service, ported from the original Cyclone-AI-Guideline-Handover Next.js app (internal only, port 8000, called via `PREPAREDNESS_SERVICE_URL`)
- `services/ccm/` — CCM model microservice stub
- Celery `worker` + `beat` — background jobs

## Data
- Postgres/PostGIS (`db`), Redis (`redis`), MinIO (`minio`) — all containers
- Migrations: Alembic, inside the `api` container. **Never auto-run — always manual**, on both local and VM.

## Compose files — do not mix these up
- `docker-compose.yml` — local dev
- `docker-compose.vm.yml` — production, VM only

## Git-ignored (must exist locally before building)
- `services/dfrm/assets/`, `services/preparedness/assets/`
- Setup scripts: `scripts/dfrm_setup_assets.py`, `scripts/setup-preparedness-assets.sh`
- `.env` — secrets, never read into context, never commit, never print

## Deployment
Fully manual. No CI runner. Flow: push to `main` on `github.com/mahmudasiif/forewarn_ibf` → on VM: `git pull` → `docker compose -f docker-compose.vm.yml up -d --build <service>` → migrations run by hand, separately, only when needed.

## Known landmines
- `docker-compose.prod.yml` still uses `ports: []` to try to clear the base file's
  published ports as an overlay. That trick is **proven broken** — Compose appends
  list fields across `-f` files instead of replacing them, so `ports: []` does
  nothing and the base ports leak through. This was found and fixed the hard way
  on a real VM deploy (see "Deployment history" below) — `docker-compose.vm.yml`
  was rewritten standalone specifically to avoid this. `docker-compose.prod.yml`
  was never fixed and isn't listed in this file's own "Compose files" section
  above, so it looks unused. Confirm that before anyone runs it; if it's needed,
  rewrite it standalone the same way.
- `auth/` and `health/` API modules are empty scaffolding — router files exist,
  zero actual endpoints registered. Some older project docs describe these as
  "implemented." They are not. Don't trust that claim elsewhere without checking
  the actual router.py.
- Migrations are manual-only by design (see "Data" above) — check
  `alembic current` against whatever database you're pointed at before assuming
  a migration has run. Preparedness (`20260914_..._preparedness_schema.py`) and
  DFRM (`20260918_..._dfrm_schema.py`) migrations exist in the repo; whether
  they've been applied to any given database is a separate question.

## Deployment history (context, not current state)
The FOREWARN portal was previously built and deployed from a different local
repo (`D:\Projects\ibf-portal`, now superseded by this one) to the client's
model VM (`10.71.1.102`). Only CCM existed at that point — it went live there
with 29,887 real result rows imported from the CCM v2.9.3 package, reachable
through an nginx vhost on port 8080. That deployment surfaced several real bugs
worth knowing if this repo (with DFRM + Preparedness added) ever gets deployed
to the same or another VM:
- TanStack Router: a `route()` helper wrapping `createRoute()` must type its
  `path` param as a generic `<TPath extends string>`, not plain `string`, or
  every `Link to=` silently degrades to only `"/" | "." | ".."`. Invisible in
  `npm run dev` (no typecheck) — only `npm run build` catches it.
- Docker Compose overlay files (`-f base.yml -f overlay.yml`) merge list
  fields like `ports`/`volumes` by *appending*, not replacing — a plain
  `ports: []` in the overlay does nothing. The `!reset`/`!override` merge
  tags exist to fix that but were unreliable in practice on this project (both
  produced an empty field instead of the intended replacement, for reasons not
  fully root-caused). Go standalone instead — one full compose file, no
  merging at all — as `docker-compose.vm.yml` now does.
- A service's `command:` set in the base dev compose file silently carries into
  a prod-target override unless explicitly set to `null` there — a prod nginx
  image trying to run the dev file's `npm run dev` command crash-loops with
  exit 127.
- Check `ss -tlnp` for whatever port you pick for a new nginx vhost before
  assuming it's free — a forgotten unrelated process can already own it.
- `.env`'s `DATABASE_URL` repeats the DB password separately from
  `POSTGRES_PASSWORD` — the two must match by hand; nothing enforces it.

Full narrative and exact commands are in that Claude session's history, not
reproduced here to save tokens — ask the user if the detail is needed.

## Status as of 2026-09-18 / next steps
- Git was just wired up in this working copy (it was a plain file copy with no
  `.git` before today) — `origin` → `github.com/mahmudasiif/forewarn_ibf`,
  `main` checked out clean against it, no drift.
- `.env` exists locally; was missing `DFRM_SERVICE_URL` / `DFRM_REQUEST_TIMEOUT`
  (both have safe defaults in `core/config.py`, so this was cosmetic, not
  blocking) — added by hand.
- First `docker compose up -d --build` (local dev stack): everything came up
  except `web-1`, which crash-loops with
  `ERR_MODULE_NOT_FOUND ... node_modules/dist/node/cli.js`. Classic stale
  anonymous-volume issue — `docker-compose.yml` mounts an anonymous
  `/app/node_modules` volume to stop the (empty, Windows-side) host
  `node_modules` from shadowing the container's install, but that volume
  persists old contents across rebuilds unless explicitly recreated. Worth
  noting: this compose file still uses `name: forewarn-ibf`, the *same*
  Compose project name as the old `ibf-portal` repo — if that repo ever ran on
  this same Docker Desktop, its `web` anonymous volume may literally still be
  the one being reused here, which would explain a completely mismatched
  `node_modules` layout. Fix in progress:
  `docker compose up -d --build -V web` (the `-V` flag forces anonymous
  volumes to be recreated).

**Next steps, in order:**
1. Confirm the `-V web` fix actually resolves `web-1`.
2. Once every container is up, spot-check each one: `api` `/api/v1/ccm/cyclones`
   (should return real data, matches the earlier VM import), `dfrm`/`preparedness`
   `/health` and `/info` (preparedness takes 1–3 min to report ready — GIS
   warm-load on boot, not a failure), `web` loads in a browser.
3. Decide whether `docker-compose.prod.yml` should be deleted or rewritten
   (see "Known landmines").
4. Auth (Module 1) is still fully unbuilt — stub router only. Needs: 4 roles
   (Super Admin / Admin / Registered Viewer / General Viewer), JWT access +
   rotating refresh tokens, permission-based route guards (not pure role
   checks).
5. `/health` and `/health/ready` — router registered, zero endpoints. Small,
   worth doing before any real deployment so uptime monitoring has something
   to hit.
6. Before deploying this repo anywhere: confirm with the user whether it still
   targets the same model VM (`10.71.1.102`) and whether the old `ibf-portal`
   deployment there should be torn down or coexist.