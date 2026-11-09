.PHONY: up down restart build logs ps clean help gateway setup-db venv-check

# Environment Detection
DOCKER_AVAILABLE := $(shell docker info > /dev/null 2>&1 && echo yes || echo no)
VENV_EXISTS := $(shell [ -d .venv ] && echo yes || echo no)

# Execution Prefix
# Using dagster-daemon as it has all consolidated dependencies from root requirements.txt
# We override hosts and ports to use internal Docker service names and standard ports
DOCKER_RUN = docker compose run --rm \
	-e PYTHONPATH=. \
	-e POSTGRES_HOST=postgres \
	-e POSTGRES_PORT=5432 \
	-e CLICKHOUSE_HOST=clickhouse \
	-e CLICKHOUSE_PORT=8123 \
	-e TERMINAL_CH_HOST=clickhouse \
	-e TERMINAL_CH_PORT=8123 \
	-e TERMINAL_CH_USER=admin \
	-e TERMINAL_CH_PASS=admin_password \
	-e TERMINAL_CH_DB=terminal \
	dagster-daemon
EXEC = $(if $(filter yes,$(DOCKER_AVAILABLE)),$(DOCKER_RUN),PYTHONPATH=. python3)

# Default target
help:
	@echo "The-Terminal Infrastructure Management"
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  up      : Create network and start all services"
	@echo "  down    : Stop and remove all services"
	@echo "  restart : Restart all services"
	@echo "  build   : Rebuild all images"
	@echo "  logs    : Tail logs for all services"
	@echo "  ps      : Show status of all containers"
	@echo "  clean   : Deep clean of all docker resources (containers, images, volumes)"
	@echo "  gateway : Start/Restart only the gateway service"
	@echo "  setup-db: Initialize all databases using containerized context"

up:
	@bash scripts/bootstrap.sh

gateway:
	docker compose up -d gateway

down:
	docker compose down

restart:
	docker compose restart

build:
	docker compose build

logs:
	docker compose logs -f

ps:
	docker compose ps

setup-db: venv-check
	@echo "🔧 Initializing databases (Postgres)..."
	@$(EXEC) python3 scripts/setup_db.py
	@echo "📈 Initializing ClickHouse (New Storage)..."
	@$(EXEC) python3 scripts/init_clickhouse.py

init-clickhouse: venv-check
	@$(EXEC) python3 scripts/init_clickhouse.py

venv-check:
	@if [ "$(VENV_EXISTS)" = "yes" ]; then \
		if [ "requirements.txt" -nt ".venv/.last_sync" ]; then \
			echo ""; \
			echo "⚠️  WARNING: Local .venv might be out of sync with requirements.txt"; \
			echo "   Run 'pip install -r requirements.txt && touch .venv/.last_sync' to update."; \
			echo ""; \
		fi \
	fi

clean:
	@echo "⚠️ Warning: This will remove all containers, images, and volumes!"
	docker compose down -v --rmi all --remove-orphans
	docker system prune -f
	docker network rm the-terminal-network || true
