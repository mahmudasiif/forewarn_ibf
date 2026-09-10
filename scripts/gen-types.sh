#!/usr/bin/env bash
# Regenerate the frontend's API types from the running API's OpenAPI schema.
set -euo pipefail
API_URL="${API_URL:-http://localhost:8000/openapi.json}"
echo "Generating types from $API_URL ..."
cd "$(dirname "$0")/../apps/web"
npx openapi-typescript "$API_URL" -o src/types/api.d.ts
echo "Wrote apps/web/src/types/api.d.ts"
