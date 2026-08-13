.DEFAULT_GOAL := help
.PHONY: help up down dev dev-down logs test-backend test-frontend smoke \
        rebuild rebuild-lean db-reset db-reset-dev

help: ## Show this list of commands
	@echo "AIOps Platform Assistant — available commands:"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z0-9_-]+:.*##/ { printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

up: ## Start the full stack (Postgres, Redis, Celery, nginx, Prometheus/Grafana/Loki)
	docker compose up -d

down: ## Stop the full stack
	docker compose down

dev: ## Start the fast dev stack (SQLite, mock LLM, no Redis/nginx/observability)
	docker compose -f docker-compose.dev.yml up

dev-down: ## Stop the fast dev stack
	docker compose -f docker-compose.dev.yml down

logs: ## Tail backend + frontend logs from the full stack
	docker compose logs -f backend frontend

# Two adjustments are needed to make the containerised run match CI, which runs
# the suite from a full checkout:
#   1. The compose-config tests resolve repo-root paths via
#      Path(__file__).resolve().parents[2]. The image's /app/backend -> /app
#      symlink collapses that to /, and deploy/, scripts/, .github/ and
#      .env.production.example are not in the image at all (build context is
#      ./backend). Mounting them read-only at / is what those tests look for.
#   2. `docker compose run backend` inherits the service environment, so
#      CELERY_BROKER_URL points at the compose Redis and outranks the
#      REDIS_URL a test monkeypatches. CI sets neither, so unset them here.
# Without these, the suite reports 9 failures that CI does not have.
test-backend: ## Run the backend test suite inside Docker
	docker compose run --rm -e DATABASE_URL=sqlite:////tmp/test.db \
	  -v "$(CURDIR)/deploy:/deploy:ro" \
	  -v "$(CURDIR)/scripts:/scripts:ro" \
	  -v "$(CURDIR)/.github:/.github:ro" \
	  -v "$(CURDIR)/.env.production.example:/.env.production.example:ro" \
	  backend env -u CELERY_BROKER_URL -u CELERY_RESULT_BACKEND -u RATELIMIT_STORAGE_URL -u REDIS_URL \
	  python -m pytest backend/tests/ -q

test-frontend: ## Run the frontend test suite
	npm run test

smoke: ## Run the smoke test (needs a server already running on :8000)
	python3 scripts/mock_portal_smoke.py

rebuild: ## Rebuild the full stack images from scratch, no cache
	docker compose build --no-cache

rebuild-lean: ## Rebuild the fast dev image from scratch, no cache
	docker compose -f docker-compose.dev.yml build --no-cache

db-reset: ## Wipe the full stack's data (Postgres, Redis, Prometheus, Grafana) and restart
	docker compose down -v
	docker compose up -d

db-reset-dev: ## Wipe the fast dev stack's SQLite data and restart
	docker compose -f docker-compose.dev.yml down -v
	docker compose -f docker-compose.dev.yml up
