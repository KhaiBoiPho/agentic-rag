# Auto-detect Docker socket (works on Docker Desktop macOS, Docker Engine Linux)
DOCKER_SOCK := $(or \
  $(wildcard /var/run/docker.sock), \
  $(wildcard $(HOME)/.docker/desktop/docker.sock), \
  $(wildcard $(HOME)/.docker/run/docker.sock))

ifneq ($(DOCKER_SOCK),)
  export DOCKER_HOST := unix://$(DOCKER_SOCK)
endif

DC := docker compose

.PHONY: setup build up down restart logs shell \
        migrate migrate-down migrate-gen \
        test lint fmt \
        monitoring help

# ─── First-time setup ─────────────────────────────────────────────────────────
setup:
	@bash scripts/setup.sh

# ─── Docker lifecycle (development) ───────────────────────────────────────────
build:
	$(DC) build --no-cache

up:
	$(DC) up -d postgres qdrant rabbitmq migrate app ui

down:
	$(DC) down

restart:
	$(DC) restart app

logs:
	$(DC) logs -f app

logs-all:
	$(DC) logs -f

shell:
	$(DC) exec app bash

# ─── Monitoring ───────────────────────────────────────────────────────────────
monitoring:
	$(DC) --profile monitoring up -d prometheus grafana

# ─── Database ─────────────────────────────────────────────────────────────────
migrate:
	$(DC) run --rm migrate alembic upgrade head

migrate-down:
	$(DC) run --rm migrate alembic downgrade -1

migrate-gen:
	@test -n "$(msg)" || (echo "Usage: make migrate-gen msg='your message'"; exit 1)
	$(DC) run --rm migrate alembic revision --autogenerate -m "$(msg)"

# ─── Local dev (without Docker) ───────────────────────────────────────────────
dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# ─── Testing ──────────────────────────────────────────────────────────────────
test:
	pytest -v --cov=app --cov-report=term-missing

test-fast:
	pytest -v -x --no-cov

# ─── Code quality ─────────────────────────────────────────────────────────────
lint:
	ruff check app/

lint-fix:
	ruff check --fix app/

fmt:
	ruff format app/

fmt-check:
	ruff format --check app/

# ─── Help ─────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  make setup          First-time setup (copies .env, generates secrets)"
	@echo "  make up             Start all services (dev)"
	@echo "  make down           Stop all services"
	@echo "  make logs           Tail app logs"
	@echo "  make shell          Shell into app container"
	@echo "  make migrate        Run DB migrations"
	@echo "  make migrate-gen    Generate migration  (msg='description')"
	@echo "  make test           Run tests with coverage"
	@echo "  make lint           Run ruff linter"
	@echo "  make fmt            Format code with ruff"
	@echo "  make monitoring     Start Prometheus + Grafana"
	@echo ""
	@echo "  Services (dev):"
	@echo "    UI          http://localhost:3210"
	@echo "    API         http://localhost:8000/docs"
	@echo "    RabbitMQ    http://localhost:15672  (guest/guest)"
	@echo "    Qdrant      http://localhost:6333"
	@echo "    Prometheus  http://localhost:9090"
	@echo "    Grafana     http://localhost:3001   (admin/admin)"
	@echo ""
