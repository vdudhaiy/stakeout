
.PHONY: help install sync \
        backend frontend dashboard \
        test coverage \
        docker-up docker-down docker-logs docker-reset

help: ## Show this list of commands
	@grep -E '^[a-zA-Z_-]+:.*## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "%-14s %s\n", $$1, $$2}'

# ── Environment ──────────────────────────────────────────────────────────────

install: ## Install/sync Python dependencies
	uv sync

sync: install ## Alias for install

# ── Dashboard ─────────────────────────────────────────────────────────────────

backend: ## Run the FastAPI backend with auto-reload
	cd backend/src && uv run uvicorn main:app --reload

frontend: ## Run the Vite frontend dev server
	cd frontend && npm run dev

# ── Docker (local / self-hosted) ─────────────────────────────────────────────

docker-up: ## Build and start the full stack via Docker Compose
	docker compose up --build -d
	@echo "Stakeout is starting at http://localhost:3000"

docker-down: ## Stop the Docker Compose stack
	docker compose down

docker-logs: ## Tail logs from the Docker Compose stack
	docker compose logs -f

docker-reset: ## Stop containers AND wipe the Postgres volume (deletes local accounts/portfolios)
	docker compose down -v

# ── Tests ─────────────────────────────────────────────────────────────────────

test: ## Run the backend test suite
	uv run --group dev pytest -v

coverage: ## Run tests with coverage (terminal + HTML report)
	uv run --group dev pytest --cov=backend/src --cov-report=term-missing --cov-report=html
	@echo "HTML report: htmlcov/index.html"
