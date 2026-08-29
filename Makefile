# OpenTrading — development entrypoints.
# Core runtime is Python 3.12 (INV-13), managed with uv.
# Local infrastructure is Docker Compose (infra/compose). See
# docs/runbooks/local-development.md and docs/runbooks/infrastructure.md.

COMPOSE ?= docker compose
DEV_COMPOSE := $(COMPOSE) --project-name opentrading-dev -f infra/compose/docker-compose.yml --env-file .env
PROD_FILES := -f infra/compose/docker-compose.yml -f infra/compose/docker-compose.prod.yml

.PHONY: setup env-file lint format typecheck test test-unit test-integration ci \
        up down ps logs health migrate migrate-down init-buckets reset-dev up-prod \
        security-scan deps-audit verify-secrets

setup:
	uv sync --all-groups

env-file:
	@test -f .env || { echo "info: creating .env from .env.example (dev-only placeholders)"; cp .env.example .env; }

# ── Local infrastructure (Docker Compose) ────────────────────────────────────
# One command starts the complete dev environment: containers, MinIO buckets,
# database migrations. `--wait` returns only when every service is healthy.
up: env-file
	$(DEV_COMPOSE) up -d --build --wait
	$(DEV_COMPOSE) run --rm minio-init
	$(MAKE) migrate

down:
	$(DEV_COMPOSE) down --remove-orphans

ps:
	$(DEV_COMPOSE) ps

logs:
	$(DEV_COMPOSE) logs -f --tail=200 $(SERVICE)

health:
	$(DEV_COMPOSE) ps
	uv run python scripts/infra_health.py

migrate: env-file
	uv run alembic upgrade head

migrate-down: env-file
	uv run alembic downgrade -1

init-buckets:
	$(DEV_COMPOSE) run --rm minio-init

# Destroys all dev volumes (irreversible) and rebuilds the environment.
reset-dev:
	@read -p "This destroys ALL dev volumes (irreversible). Continue? [y/N] " answer; \
		test "$$answer" = "y" || { echo "aborted"; exit 1; }
	$(DEV_COMPOSE) down -v --remove-orphans
	$(MAKE) up

# Production: same services, no published ports, internal-only network,
# secrets required (fails closed when any secret is missing). Secrets come
# from the SOPS-encrypted env file — see docs/runbooks/secrets-management.md.
up-prod:
	$(COMPOSE) --project-name opentrading-prod $(PROD_FILES) --env-file .env.prod up -d --build --wait

# ── Python runtime ───────────────────────────────────────────────────────────
lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy core apps engines adapters

test:
	uv run pytest

test-unit:
	uv run pytest tests/unit

test-integration:
	OT_INTEGRATION=1 uv run pytest -m integration

# ── Security gates (ADR-0025; CI runs these on every push) ───────────────────
security-scan:
	@command -v gitleaks >/dev/null 2>&1 || { echo "error: gitleaks not installed"; exit 1; }
	gitleaks git --redact

deps-audit:
	uv export --all-groups --format requirements-txt -o /tmp/opentrading-requirements.txt
	uvx pip-audit -r /tmp/opentrading-requirements.txt --progress-spinner off

verify-secrets:
	scripts/secrets/verify.sh

ci: lint typecheck test
