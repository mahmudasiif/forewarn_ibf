# FOREWARN Bangladesh — Impact-Based Forecasting (IBF) Portal

Monorepo for the FOREWARN IBF Portal: a React dashboard, a FastAPI core API,
and a set of containerised AI/ML model services (CCM first).

> The public FOREWARN **Website** is a separate repository. It will talk to this
> portal over the API — never over the database.

## Quick start

```bash
cp .env.example .env
make up          # builds and starts the whole stack
make migrate     # apply database migrations
make seed        # load reference data
```

| Service | URL | Notes |
|---|---|---|
| Web dashboard | http://localhost:5173 | Vite dev server |
| Core API | http://localhost:8000/docs | FastAPI + OpenAPI |
| CCM model | http://localhost:8101/docs | model micro-service |
| MinIO console | http://localhost:9001 | object storage |
| Postgres | localhost:5432 | PostGIS 3.x on PG 18 |

## Layout

```
apps/       things people use          — web (React), api (FastAPI)
services/   things the API calls       — ccm, _template, worker
packages/   things both share          — contracts (OpenAPI + TS types)
infra/      how it runs                — docker, nginx, env
Documents/  the project brain          — gitignored, local reference
```

Full architecture, data model, API catalog and the development plan live in
`Documents/`. Start with `Documents/00-README.md`.

## Common commands

```bash
make up / make down / make logs
make migrate            # alembic upgrade head
make revision m="..."   # new migration
make types              # regenerate frontend types from the API OpenAPI schema
make test               # backend + frontend test suites
make fmt                # ruff + prettier
```
