# Contracts

The API's OpenAPI schema is the contract between backend and frontend.

- `openapi.json` — snapshot exported from the running API (`make types` also refreshes it).
- Frontend types are generated from it into `apps/web/src/types/api.d.ts`.

Never hand-write a type that the schema already describes. If the frontend needs a shape
the API does not expose, change the API — not the generated file.
