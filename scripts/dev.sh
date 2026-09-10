#!/usr/bin/env bash
# First-run helper: copy env, build, start, migrate, seed.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { cp .env.example .env; echo "Created .env — edit the secrets before production."; }
docker compose up -d --build
echo "Waiting for the API ..."
until curl -sf http://localhost:8000/api/v1/health >/dev/null; do sleep 2; done
docker compose exec api alembic upgrade head
echo "Ready:  dashboard http://localhost:5173  |  API http://localhost:8000/docs"
