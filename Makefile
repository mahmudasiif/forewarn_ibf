COMPOSE = docker compose

.PHONY: up down build logs ps restart migrate revision seed types test fmt lint shell-api shell-db clean

up:            ## Build and start the full dev stack
	$(COMPOSE) up -d --build

down:          ## Stop the stack
	$(COMPOSE) down

build:
	$(COMPOSE) build

logs:
	$(COMPOSE) logs -f --tail=100

ps:
	$(COMPOSE) ps

restart:
	$(COMPOSE) restart

migrate:       ## Apply database migrations
	$(COMPOSE) exec api alembic upgrade head

revision:      ## make revision m="add hazard tables"
	$(COMPOSE) exec api alembic revision --autogenerate -m "$(m)"

seed:          ## Load reference/seed data
	$(COMPOSE) exec api python -m scripts.seed

types:         ## Regenerate frontend types from the API OpenAPI schema
	bash scripts/gen-types.sh

test:
	$(COMPOSE) exec api pytest -q
	cd apps/web && npm run test --if-present

fmt:
	$(COMPOSE) exec api ruff format app
	cd apps/web && npm run format --if-present

lint:
	$(COMPOSE) exec api ruff check app
	cd apps/web && npm run lint

shell-api:
	$(COMPOSE) exec api bash

shell-db:
	$(COMPOSE) exec db psql -U forewarn -d forewarn

clean:
	$(COMPOSE) down -v --remove-orphans
